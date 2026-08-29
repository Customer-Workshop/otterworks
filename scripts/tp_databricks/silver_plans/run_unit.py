"""Run the silver_plans unit against live Oracle and the shared workspace, and measure the recon.

Sequence, once per invocation:

1. verify the pinned Oracle source SHA (stop if it moved),
2. derive the run's `sp_change_plan` request population from the source by the spec's rule, then
   snapshot the source read-only: counts, `fn_list_plans`, `fn_entitlement` per tenant, and the
   result `sp_change_plan` *would* leave — re-expressed as SELECTs and evaluated by Oracle, because
   the procedure mutates `SUBSCRIPTIONS` and is never called,
3. deploy the notebook and its column spec under the parent-owned notebook root,
4. run the notebook twice on serverless with identical inputs,
5. recompute counts, money, types, checksums and every target row **from the Delta targets** over
   the SQL warehouse, independently of what the notebook reported,
6. compare against Oracle row by row and against the five pinned Oracle transcripts one by one,
7. write the recon report.

Nothing here writes to Oracle, to `ow_tp.bronze.*`, or to any table this unit does not own, and no
compute resource is ever created: the notebook runs on serverless and the recon SQL goes to the
pre-existing warehouse.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import pathlib
import sys
from typing import Any

from scripts.tp_databricks.bronze_core.dbx_client import Dbx, DbxError, sql_str
from scripts.tp_databricks.silver_plans import oracle_truth

ROOT = pathlib.Path(__file__).resolve().parents[3]
UNIT = "silver_plans"
CATALOG = "ow_tp"
SCHEMA = "silver"
BRONZE = "bronze"
NOTEBOOK_ROOT = "/Shared/ow_tp"
LANDING_ROOT = "/Volumes/ow_tp/bronze/landing"
NOTEBOOK_LOCAL = ROOT / "databricks" / "notebooks" / "ow_tp_silver_plans.py"
SPEC_LOCAL = ROOT / "databricks" / "ddl" / "silver_plans_spec.json"
REPORT_PATH = ROOT / "docs" / "tech-partnerships" / "recon" / f"{UNIT}.recon.json"
TRANSCRIPT_DIR = ROOT / "procs" / "oracle" / "transcripts" / "plans"
PINNED_SHA_FILE = ROOT / "procs" / "oracle" / "transcripts" / "ORACLE_SOURCE_SHA"
SEED_MANIFEST = ROOT / "testdata" / "legacy" / "manifests"

SPEC = json.loads(SPEC_LOCAL.read_text())
CONST = SPEC["plans_constants"]
TABLES = {t["target"]: t for t in SPEC["tables"]}
COLUMN_CLASS = {
    f"{t['target']}.{c['name']}": c["class"] for t in SPEC["tables"] for c in t["columns"]
}
TARGET_TYPE = {
    f"{t['target']}.{c['name']}": c["target_type"] for t in SPEC["tables"] for c in t["columns"]
}
OVERRIDES = SPEC["change_requests"]["overrides_are_pinned_from_transcripts"]
ENTITLEMENT_ON = SPEC["entitlement_on"]
CHANGE_EFFECTIVE_ON = SPEC["change_requests"]["default_effective_on"]
STATUS_MAP = {int(k): v for k, v in CONST["status_map"].items()}

# The columns compared row by row against live Oracle, per target, and the class each is normalised
# in. Money to the cent (T1), counts and codes as integers, timestamps as the source's own
# 'YYYY-MM-DD HH24:MI:SS' text so a carried time component is visible rather than rounded away.
PLAN_COLS: dict[str, str] = {
    "code": "text",
    "tier_cd": "code",
    "tier": "text",
    "monthly_fee": "money",
    "included_units": "count",
    "overage_rate": "rate",
    "active_yn": "text",
    "active_nvl": "text",
    "listed_by_fn_list_plans": "flag",
}
ENT_COLS: dict[str, str] = {
    "subscription_id": "text",
    "plan_id": "text",
    "plan_code": "text",
    "tier": "text",
    "monthly_fee": "money",
    "included_units": "count",
    "status_cd": "code",
    "subscription_status": "text",
    "effective_on": "ts",
    "starts_on": "ts",
    "ends_on": "ts",
    "candidate_rows": "code",
    "tied_starts_on_rows": "code",
    "plan_null_extended": "flag",
    "cursor_predicate_covers": "flag",
    "sentinel_predicate_covers": "flag",
}
SUB_COLS: dict[str, str] = {
    "tenant_id": "text",
    "plan_id": "text",
    "starts_on": "ts",
    "ends_on": "ts",
    "status_cd": "code",
}

EXPECTED_ANOMALIES = [
    "ANOM-SENTINEL-DATE",
    "ANOM-ROWNUM-TIEBREAK",
    "ANOM-ROWBYROW-CLOSEOUT",
    "ANOM-PKG-GLOBAL-STATE",
    "ANOM-DYNAMIC-SQL",
    "ANOM-SWALLOWED-EXCEPTION",
]

MONEY_COLUMNS = ("plans.monthly_fee", "entitlements.monthly_fee")


class Halt(RuntimeError):
    """A stop-and-report condition from the unit's brief, not a bug."""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(
    cid: str, expected: Any, actual: Any, sot: str, passed: bool | None = None, **extra: Any
) -> dict[str, Any]:
    ok = (expected == actual) if passed is None else passed
    row = {
        "id": cid,
        "expected": expected,
        "actual": actual,
        "source_of_truth": sot,
        "result": "pass" if ok else "fail",
    }
    row.update(extra)
    return row


SCALES = {
    "money": decimal.Decimal("0.01"),
    "rate": decimal.Decimal("0.000001"),
    "count": decimal.Decimal("1"),
}


def norm(value: Any, cls: str) -> Any:
    """One normalisation for both sides, driven by the frozen spec's own column class."""
    if value is None:
        return None
    if cls in SCALES:
        return str(decimal.Decimal(str(value)).quantize(SCALES[cls]))
    if cls == "flag":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "y")
    if cls == "code":
        return int(value)
    if cls == "ts":
        # The warehouse hands timestamps back as 'YYYY-MM-DD HH:MM:SS[.f]'; Oracle's side is already
        # TO_CHAR'd to the second. Both are compared as second-precision wall-clock text.
        text = str(value).replace("T", " ")
        return text.split(".")[0] if "." in text else text
    return value


# -- deploy / run --------------------------------------------------------------


def deploy(dbx: Dbx) -> None:
    dbx.mkdirs_workspace(NOTEBOOK_ROOT)
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/ow_tp_silver_plans",
        str(NOTEBOOK_LOCAL),
        fmt="SOURCE",
        language="PYTHON",
    )
    dbx.import_workspace(f"{NOTEBOOK_ROOT}/silver_plans_spec.json", str(SPEC_LOCAL), fmt="AUTO")


def run_notebook(dbx: Dbx, ns: str, batch_id: str) -> dict[str, Any]:
    run_id = dbx.submit_notebook_run(
        run_name=f"ow_tp_silver_plans_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_plans",
        params={
            "ns": ns,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "bronze_schema": BRONZE,
            "entitlement_on": ENTITLEMENT_ON,
            "change_effective_on": CHANGE_EFFECTIVE_ON,
            "landing_root": LANDING_ROOT,
            "spec_path": f"{NOTEBOOK_ROOT}/silver_plans_spec.json",
            "batch_id": batch_id,
        },
    )
    run = dbx.wait_run(run_id)
    state = (run.get("state") or {}).get("result_state") or (
        run.get("status", {}).get("termination_details", {}).get("code")
    )
    if state not in ("SUCCESS", "SUCCESS_WITH_FAILURES", None):
        out = dbx.run_output(run_id)
        raise DbxError(
            f"silver_plans notebook run {run_id} ended {state}: "
            f"{json.dumps(out.get('error') or out)[:4000]}"
        )
    summary = json.loads(
        dbx.read_volume_file(f"{LANDING_ROOT}/{ns}/{UNIT}/_runs/{batch_id}.json").decode()
    )
    summary["run_id"] = run_id
    # The workspace host stays out of the branch, so only the host-relative run path is kept.
    url = run.get("run_page_url") or ""
    summary["run_page_path"] = url.split("cloud.databricks.com", 1)[-1] if url else None
    return summary


# -- target side, recomputed from Delta ---------------------------------------


def target_snapshot(dbx: Dbx, ns: str) -> dict[str, Any]:
    """Every target number in the report, read back out of Delta after the MERGEs."""
    ns_lit = sql_str(ns)
    counts = {}
    for name in ("plans", "subscriptions", "entitlements", f"quarantine_{UNIT}"):
        counts[name] = int(
            dbx.sql(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{name} WHERE ns = {ns_lit}")[0][0]
        )
    other_ns = {
        name: int(
            dbx.sql(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{name} WHERE ns <> {ns_lit}")[0][0]
        )
        for name in ("plans", "subscriptions", "entitlements")
    }
    rows_without_ns = {
        name: int(
            dbx.sql(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{name} WHERE ns IS NULL")[0][0]
        )
        for name in ("plans", "subscriptions", "entitlements")
    }

    plan_rows = [
        dict(
            zip(
                (
                    "id", "code", "tier_cd", "tier", "monthly_fee", "included_units",
                    "overage_rate", "active_yn", "active_nvl", "listed_by_fn_list_plans",
                    "list_seq", "_origin", "_batch_id",
                ),
                r,
            )
        )
        for r in dbx.sql(
            f"""
            SELECT id, code, CAST(tier_cd AS STRING), tier, CAST(monthly_fee AS STRING),
                   CAST(included_units AS STRING), CAST(overage_rate AS STRING), active_yn,
                   active_nvl, CAST(listed_by_fn_list_plans AS STRING), CAST(list_seq AS STRING),
                   _origin, _batch_id
            FROM {CATALOG}.{SCHEMA}.plans WHERE ns = {ns_lit} ORDER BY id
            """
        )
    ]
    sub_rows = [
        dict(
            zip(
                (
                    "id", "tenant_id", "plan_id", "starts_on", "ends_on", "status_cd",
                    "suspended_on", "status_cd_before", "ends_on_before", "closed_by_change",
                    "closeout_seq", "change_effective_on", "change_plan_id",
                    "reactivated_from_suspended", "cancelled_preserved",
                    "overlaps_new_subscription", "_origin", "_batch_id",
                ),
                r,
            )
        )
        for r in dbx.sql(
            f"""
            SELECT id, tenant_id, plan_id, CAST(starts_on AS STRING), CAST(ends_on AS STRING),
                   CAST(status_cd AS STRING), CAST(suspended_on AS STRING),
                   CAST(status_cd_before AS STRING), CAST(ends_on_before AS STRING),
                   CAST(closed_by_change AS STRING), CAST(closeout_seq AS STRING),
                   CAST(change_effective_on AS STRING), change_plan_id,
                   CAST(reactivated_from_suspended AS STRING), CAST(cancelled_preserved AS STRING),
                   CAST(overlaps_new_subscription AS STRING), _origin, _batch_id
            FROM {CATALOG}.{SCHEMA}.subscriptions WHERE ns = {ns_lit} ORDER BY tenant_id, id
            """
        )
    ]
    ent_rows = [
        dict(
            zip(
                (
                    "tenant_id", "as_of_on", "subscription_id", "plan_id", "plan_code", "tier",
                    "monthly_fee", "included_units", "status_cd", "subscription_status",
                    "effective_on", "starts_on", "ends_on", "candidate_rows",
                    "tied_starts_on_rows", "plan_null_extended", "cursor_predicate_covers",
                    "sentinel_predicate_covers", "predicates_disagree", "global_lookup_matched",
                    "global_lookup_plan_code", "global_lookup_candidate_rows",
                    "global_iteration_seq", "stale_global_plan_code", "stale_global_mismatch",
                    "_origin", "_batch_id",
                ),
                r,
            )
        )
        for r in dbx.sql(
            f"""
            SELECT tenant_id, CAST(as_of_on AS STRING), subscription_id, plan_id, plan_code, tier,
                   CAST(monthly_fee AS STRING), CAST(included_units AS STRING),
                   CAST(status_cd AS STRING), subscription_status, CAST(effective_on AS STRING),
                   CAST(starts_on AS STRING), CAST(ends_on AS STRING),
                   CAST(candidate_rows AS STRING), CAST(tied_starts_on_rows AS STRING),
                   CAST(plan_null_extended AS STRING), CAST(cursor_predicate_covers AS STRING),
                   CAST(sentinel_predicate_covers AS STRING), CAST(predicates_disagree AS STRING),
                   CAST(global_lookup_matched AS STRING), global_lookup_plan_code,
                   CAST(global_lookup_candidate_rows AS STRING), CAST(global_iteration_seq AS STRING),
                   stale_global_plan_code, CAST(stale_global_mismatch AS STRING), _origin, _batch_id
            FROM {CATALOG}.{SCHEMA}.entitlements
            WHERE ns = {ns_lit} AND as_of_on = TIMESTAMP'{ENTITLEMENT_ON} 00:00:00'
            ORDER BY tenant_id
            """
        )
    ]
    quar_rows = [
        {
            "quarantine_reason": r[0],
            "source_table": r[1],
            "source_key": r[2],
            "detail": r[3],
            "_batch_id": r[4],
            "rows": int(r[5]),
        }
        for r in dbx.sql(
            f"""
            SELECT quarantine_reason, source_table, source_key, min(detail), min(_batch_id),
                   count(*)
            FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = {ns_lit}
            GROUP BY quarantine_reason, source_table, source_key
            ORDER BY source_table, quarantine_reason, source_key
            """
        )
    ]

    money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(monthly_fee), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN listed_by_fn_list_plans THEN monthly_fee END), 0)
                    AS STRING),
               count(*) FILTER (WHERE monthly_fee IS NULL)
        FROM {CATALOG}.{SCHEMA}.plans WHERE ns = {ns_lit}
        """
    )[0]
    ent_money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(monthly_fee), 0) AS STRING),
               count(*) FILTER (WHERE monthly_fee IS NULL),
               CAST(coalesce(sum(included_units), 0) AS STRING)
        FROM {CATALOG}.{SCHEMA}.entitlements
        WHERE ns = {ns_lit} AND as_of_on = TIMESTAMP'{ENTITLEMENT_ON} 00:00:00'
        """
    )[0]

    # Physical types, straight from the catalog: a DOUBLE anywhere on a money lineage fails the PR,
    # so the assertion is a read of the column's declared type rather than a claim.
    types: dict[str, str] = {}
    for tbl in ("plans", "subscriptions", "entitlements", f"quarantine_{UNIT}"):
        for row in dbx.sql(
            f"""
            SELECT column_name, full_data_type FROM {CATALOG}.information_schema.columns
            WHERE table_schema = '{SCHEMA}' AND table_name = '{tbl}'
            """
        ):
            types[f"{tbl}.{row[0]}"] = row[1].upper()

    return {
        "counts": counts,
        "rows_in_other_ns": other_ns,
        "rows_without_ns": rows_without_ns,
        "plan_rows": plan_rows,
        "sub_rows": sub_rows,
        "ent_rows": ent_rows,
        "quarantine_rows": quar_rows,
        "money": {
            "plans.monthly_fee_total": money[0],
            "plans.monthly_fee_total_listed_by_fn_list_plans": money[1],
            "plans.monthly_fee_null_rows": int(money[2]),
            "entitlements.monthly_fee_total": ent_money[0],
            "entitlements.monthly_fee_null_extended_rows": int(ent_money[1]),
            "entitlements.included_units_total": ent_money[2],
        },
        "column_types": types,
    }


# -- comparisons ---------------------------------------------------------------


def diff_rows(
    oracle_rows: dict[str, dict], target_rows: dict[str, dict], cols: dict[str, str], label: str
) -> dict[str, Any]:
    """Field-by-field comparison of two keyed row sets, normalised by the spec's column classes."""
    diffs = []
    for key in sorted(set(oracle_rows) | set(target_rows)):
        o, t = oracle_rows.get(key), target_rows.get(key)
        if o is None or t is None:
            diffs.append(
                {
                    "key": key,
                    "missing_from": "target" if t is None else "oracle",
                }
            )
            continue
        fields = {
            col: {"oracle": norm(o.get(col), cls), "target": norm(t.get(col), cls)}
            for col, cls in cols.items()
            if norm(o.get(col), cls) != norm(t.get(col), cls)
        }
        if fields:
            diffs.append({"key": key, "fields": fields})
    return {
        "population": label,
        "rows_compared": len(set(oracle_rows) & set(target_rows)),
        "oracle_rows": len(oracle_rows),
        "target_rows": len(target_rows),
        "rows_differing": len(diffs),
        "differences": diffs[:25],
        "columns_compared": sorted(cols),
    }


def transcript_checks(
    oracle: dict, snap: dict, pinned_sha: str
) -> list[dict[str, Any]]:
    """One measured comparison per transcript: five comparisons, not one claim."""
    plans_by_seq = sorted(
        (r for r in snap["plan_rows"] if norm(r["listed_by_fn_list_plans"], "flag")),
        key=lambda r: int(r["list_seq"]),
    )
    ent_by_tenant = {r["tenant_id"]: r for r in snap["ent_rows"]}
    subs_by_tenant: dict[str, list[dict]] = {}
    for r in snap["sub_rows"]:
        subs_by_tenant.setdefault(r["tenant_id"], []).append(r)

    checks: list[dict[str, Any]] = []
    for path in sorted(TRANSCRIPT_DIR.glob("PLANS-*.json")):
        t = json.loads(path.read_text())
        scenario, entry, fields = t["scenario"], t["oracle_entrypoint"], t["business_fields"]
        sot = (
            f"pinned Oracle transcript {path.relative_to(ROOT)} ({entry}), "
            f"oracle_source_sha {t['oracle_source_sha']}"
        )
        if t["oracle_source_sha"] != pinned_sha:
            checks.append(
                check(f"TRANSCRIPT-{scenario}", pinned_sha, t["oracle_source_sha"], sot,
                      note="transcript pinned to a different source SHA")
            )
            continue

        if entry == "pkg_plans.fn_list_plans":
            expected = {
                "codes": fields["codes"],
                "fees": [norm(v, "money") for v in fields["fees"]],
            }
            actual = {
                "codes": [r["code"] for r in plans_by_seq],
                "fees": [norm(r["monthly_fee"], "money") for r in plans_by_seq],
            }
            checks.append(
                check(
                    f"TRANSCRIPT-{scenario}",
                    expected,
                    actual,
                    sot,
                    entrypoint=entry,
                    target_object=f"{CATALOG}.{SCHEMA}.plans, the rows carrying "
                    "listed_by_fn_list_plans, in list_seq order — the function's own "
                    "ORDER BY monthly_fee, code",
                    oracle_live={
                        "codes": [p["code"] for p in oracle["list_plans"]],
                        "fees": [p["monthly_fee"] for p in oracle["list_plans"]],
                    },
                )
            )
            continue

        if entry == "pkg_plans.fn_entitlement":
            tenant = t["inputs"]["tenant_id"]
            row = ent_by_tenant.get(tenant)
            expected = {
                "plan_code": fields["plan_code"],
                "tier": fields["tier"],
                "subscription_status": fields["subscription_status"],
                "included_units": norm(fields["included_units"], "count"),
            }
            actual = (
                {
                    "plan_code": row["plan_code"],
                    "tier": row["tier"],
                    "subscription_status": row["subscription_status"],
                    "included_units": norm(row["included_units"], "count"),
                }
                if row
                else None
            )
            o = oracle["entitlements"].get(tenant, {})
            checks.append(
                check(
                    f"TRANSCRIPT-{scenario}",
                    expected,
                    actual,
                    sot,
                    tenant_id=tenant,
                    entrypoint=entry,
                    as_of=t["inputs"]["as_of"],
                    target_object=f"{CATALOG}.{SCHEMA}.entitlements for this tenant at "
                    f"as_of_on = {ENTITLEMENT_ON}",
                    oracle_live={
                        k: o.get(k)
                        for k in ("plan_code", "tier", "subscription_status", "included_units")
                    },
                )
            )
            continue

        # sp_change_plan: the SUBSCRIPTIONS state the procedure would leave for this tenant, which is
        # what the target holds after the close-out and the static insert. The procedure is never
        # called; the Oracle side of this comparison is the read-only re-expression.
        tenant = t["inputs"]["tenant_id"]
        rows = sorted(subs_by_tenant.get(tenant, []), key=lambda r: norm(r["starts_on"], "ts"))
        expected = {
            "subscriptions": [
                {
                    "plan_id": s["plan_id"],
                    "starts_on": s["starts_on"],
                    "ends_on": s["ends_on"],
                    "status": s["status"],
                }
                for s in fields["subscriptions"]
            ]
        }
        actual = {
            "subscriptions": [
                {
                    "plan_id": r["plan_id"],
                    "starts_on": norm(r["starts_on"], "ts")[:10],
                    "ends_on": None if r["ends_on"] is None else norm(r["ends_on"], "ts")[:10],
                    "status": STATUS_MAP.get(norm(r["status_cd"], "code")),
                }
                for r in rows
            ]
        }
        checks.append(
            check(
                f"TRANSCRIPT-{scenario}",
                expected,
                actual,
                sot,
                tenant_id=tenant,
                entrypoint=entry,
                inputs=t["inputs"],
                target_object=f"{CATALOG}.{SCHEMA}.subscriptions for this tenant, in starts_on "
                "order: the row the close-out loop closed and the row the static equivalent of the "
                "EXECUTE IMMEDIATE INSERT added",
                oracle_live_read_only_reexpression=[
                    {
                        "plan_id": r["plan_id"],
                        "starts_on": r["starts_on"][:10],
                        "ends_on": None if r["ends_on"] is None else r["ends_on"][:10],
                        "status": STATUS_MAP.get(r["status_cd"]),
                        "origin": r["origin"],
                    }
                    for r in oracle["change_end_state"]
                    if r["tenant_id"] == tenant
                ],
                note="sp_change_plan mutates SUBSCRIPTIONS and was not executed: the Oracle side is "
                "the read-only re-expression evaluated by Oracle (see unverified_paths)",
            )
        )
    return checks


# -- report --------------------------------------------------------------------


def seeded_scale() -> dict[str, Any]:
    manifest = SEED_MANIFEST / "demo.json"
    if not manifest.exists():
        return {"manifest": None}
    return {
        "manifest": str(manifest.relative_to(ROOT)),
        "seed": json.loads(manifest.read_text()),
        "command": "make oracle-billing-seed NS=demo SCALE=demo",
    }


def build_report(
    ns: str,
    oracle: dict,
    run1: dict,
    run2: dict,
    snap: dict,
    plan_diff: dict,
    ent_diff: dict,
    sub_diff: dict,
    pinned_sha: str,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    src = oracle["source_counts"]
    acc = run2["accounting"]
    quar = run2["quarantine"]
    ent_pop = run2["entitlement_populations"]
    chg = run2["subscription_populations"]
    o_chg = oracle["change_populations"]
    o_pop = oracle["populations"]

    checks.append(
        check(
            "SRC-SHA",
            {"oracle_source_sha": pinned_sha},
            {"oracle_source_sha": oracle["oracle_source_sha"]},
            f"{PINNED_SHA_FILE.relative_to(ROOT)} vs sha256 over "
            "services/legacy-billing/db/oracle/**/*.sql in the checked-out tree",
        )
    )
    checks.append(
        check(
            "SRC-COUNTS",
            {
                "plans": src["plans"],
                "subscriptions": src["subscriptions"],
                "tenants": src["tenants"],
            },
            {
                "plans": acc["plans"]["source_rows"],
                "subscriptions": acc["subscriptions"]["source_rows"] - chg["requests"],
                "tenants": ent_pop["tenants_in_ns"],
            },
            "live OW_BILLING counts vs the bronze slice the notebook read",
            note="the subscriptions figure is the bronze source population; the accounting basis "
            "adds one row per declared sp_change_plan request this run applies",
        )
    )

    # ACC-QUAR: the identity, per owned table, exactly.
    for name, a in acc.items():
        checks.append(
            check(
                f"ACC-QUAR-{name.upper()}",
                {"source_rows": a["source_rows"], "identity": "loaded + quarantined == source"},
                {
                    "source_rows": a["source_rows"],
                    "identity": "loaded + quarantined == source"
                    if a["loaded_rows"] + a["quarantined_rows"] == a["source_rows"]
                    else f"{a['loaded_rows']} + {a['quarantined_rows']} != {a['source_rows']}",
                },
                f"{CATALOG}.{SCHEMA}.{name}, recomputed from Delta after the MERGE",
                loaded_rows=a["loaded_rows"],
                quarantined_rows=a["quarantined_rows"],
                rate_pct=a["rate_pct"],
                basis=a["basis"],
            )
        )
    checks.append(
        check(
            "ACC-QUAR-HALT-BASIS",
            {"threshold_pct": SPEC["quarantine_halt_threshold_pct"], "over_threshold": False},
            {"threshold_pct": quar["halt_threshold_pct"], "over_threshold": quar["rate_pct"] > 5.0},
            "the single declared halt basis, numerator and denominator on the same population",
            basis=quar["basis"],
            rejected_rows=quar["rate_rejected_rows"],
            source_rows=quar["rate_source_rows"],
            rate_pct=quar["rate_pct"],
            physical_quarantine_rows=quar["physical_rows_this_run"],
            by_source_table_and_reason=quar["by_source_table_and_reason"],
            quarantine_persisted_before_the_halt_was_evaluated=quar[
                "persisted_before_halt_decision"
            ],
            closed_reason_set=SPEC["quarantine_reasons"],
        )
    )

    # Target row counts, recomputed from Delta against the source population.
    checks.append(
        check(
            "TGT-COUNTS",
            {
                "plans": src["plans"],
                "subscriptions": src["subscriptions"] + chg["requests"],
                "entitlements": acc["entitlements"]["source_rows"],
            },
            {
                "plans": snap["counts"]["plans"],
                "subscriptions": snap["counts"]["subscriptions"],
                "entitlements": len(snap["ent_rows"]),
            },
            f"count(*) over {CATALOG}.{SCHEMA}.* for ns={ns}, read back from Delta",
            quarantine_rows=snap["counts"][f"quarantine_{UNIT}"],
        )
    )

    # ACC-MONEY: exact money, both totals recomputed from the target and from Oracle's own rows.
    o_plan_money = sum(
        decimal.Decimal(p["monthly_fee"]) for p in oracle["all_plans"] if p["monthly_fee"]
    )
    o_listed_money = sum(
        decimal.Decimal(p["monthly_fee"])
        for p in oracle["all_plans"]
        if p["monthly_fee"] and p["listed_by_fn_list_plans"]
    )
    o_ent_money = sum(
        decimal.Decimal(e["monthly_fee"])
        for e in oracle["entitlements"].values()
        if e["monthly_fee"]
    )
    checks.append(
        check(
            "ACC-MONEY",
            {
                "plans.monthly_fee_total": str(o_plan_money.quantize(decimal.Decimal("0.01"))),
                "plans.monthly_fee_total_listed_by_fn_list_plans": str(
                    o_listed_money.quantize(decimal.Decimal("0.01"))
                ),
                "entitlements.monthly_fee_total": str(
                    o_ent_money.quantize(decimal.Decimal("0.01"))
                ),
            },
            {
                "plans.monthly_fee_total": norm(snap["money"]["plans.monthly_fee_total"], "money"),
                "plans.monthly_fee_total_listed_by_fn_list_plans": norm(
                    snap["money"]["plans.monthly_fee_total_listed_by_fn_list_plans"], "money"
                ),
                "entitlements.monthly_fee_total": norm(
                    snap["money"]["entitlements.monthly_fee_total"], "money"
                ),
            },
            "live Oracle PLANS/fn_entitlement money vs sum() over the Delta targets",
            quarantined_rows_alongside_these_figures=quar["physical_rows_this_run"],
            quarantine_rate_pct_on_the_declared_basis=quar["rate_pct"],
            null_money_rows={
                "plans.monthly_fee": snap["money"]["plans.monthly_fee_null_rows"],
                "entitlements.monthly_fee_null_extended": snap["money"][
                    "entitlements.monthly_fee_null_extended_rows"
                ],
            },
        )
    )
    money_types = {c: snap["column_types"].get(c) for c in MONEY_COLUMNS}
    checks.append(
        check(
            "ACC-MONEY-TYPES",
            {c: TARGET_TYPE[c] for c in MONEY_COLUMNS},
            money_types,
            f"{CATALOG}.information_schema.columns — the physical column types, not a claim",
            note="a DOUBLE or FLOAT anywhere on a money lineage fails the unit; the bronze inputs "
            "are DECIMAL and every cast in the notebook is to DECIMAL(14,2)",
        )
    )

    # Row-by-row parity, per table.
    checks.append(
        check(
            "PLANS-PARITY",
            {"rows_differing": 0, "rows_compared": plan_diff["oracle_rows"]},
            {"rows_differing": plan_diff["rows_differing"], "rows_compared": plan_diff["rows_compared"]},
            "live OW_BILLING.PLANS (with fn_list_plans' own DECODE and NVL evaluated by Oracle) vs "
            f"{CATALOG}.{SCHEMA}.plans, field by field",
            **{k: v for k, v in plan_diff.items() if k in ("columns_compared", "differences")},
        )
    )
    checks.append(
        check(
            "ENTITLEMENT-PARITY",
            {"rows_differing": 0, "rows_compared": ent_diff["oracle_rows"]},
            {"rows_differing": ent_diff["rows_differing"], "rows_compared": ent_diff["rows_compared"]},
            "fn_entitlement's returned cursor, evaluated by Oracle per tenant, vs "
            f"{CATALOG}.{SCHEMA}.entitlements, field by field",
            **{k: v for k, v in ent_diff.items() if k in ("columns_compared", "differences")},
        )
    )
    checks.append(
        check(
            "SUBSCRIPTION-PARITY",
            {"rows_differing": 0, "rows_compared": sub_diff["oracle_rows"]},
            {"rows_differing": sub_diff["rows_differing"], "rows_compared": sub_diff["rows_compared"]},
            "the SUBSCRIPTIONS end state sp_change_plan would leave — re-expressed read-only and "
            f"evaluated by Oracle — vs {CATALOG}.{SCHEMA}.subscriptions, field by field",
            **{k: v for k, v in sub_diff.items() if k in ("columns_compared", "differences")},
            note="the procedure was never executed against the source (see unverified_paths)",
        )
    )

    # ACC-SENTINEL-99: the sentinel resolves to 2099 on both sides, and no subscription expired.
    o_dialect = next(iter(oracle["dialect"].values()))
    probe = run2["dialect_probe"]
    checks.append(
        check(
            "ACC-SENTINEL-99",
            {
                "oracle_TO_DATE_31_DEC_99": "2099-12-31",
                "pinned_target_literal": "2099-12-31",
                "tenants_covered_by_the_sentinel_predicate": o_pop[
                    "tenants_covered_sentinel_predicate"
                ],
            },
            {
                "oracle_TO_DATE_31_DEC_99": o_dialect["sentinel_TO_DATE_31_DEC_99"],
                "pinned_target_literal": probe["pinned_sentinel_literal_used_by_this_port"],
                "tenants_covered_by_the_sentinel_predicate": ent_pop[
                    "tenants_covered_sentinel_predicate"
                ],
            },
            "TO_DATE('31-DEC-99','DD-MON-YY') evaluated by Oracle vs the pinned literal this port "
            "uses, with the covered population on both sides",
            spark_parse_of_the_same_literal=probe["spark_to_date_31_DEC_99"],
            spark_two_digit_year_pivot_agrees_with_oracle=probe[
                "spark_two_digit_year_pivot_agrees_with_oracle"
            ],
            note="the port pins DATE'2099-12-31' from the spec instead of parsing '31-DEC-99', "
            "because a two-digit-year pivot is a property of the engine and its session settings "
            "rather than of the source text; the runtime's own parse is measured beside it. A 1999 "
            "sentinel would have expired every open subscription, which is the bug this check is "
            "for, not a data finding",
            subscriptions_with_a_null_ends_on={
                "oracle": o_pop["subscriptions_with_a_null_ends_on"],
                "target": run2["anomaly_detections"]["ANOM-SENTINEL-DATE"][
                    "subscriptions_with_a_null_ends_on"
                ],
            },
            the_two_predicates_are_distinct={
                "cursor": "(s.ends_on IS NULL OR s.ends_on >= p_on)",
                "package_global_lookup": "NVL(s.ends_on, TO_DATE('31-DEC-99','DD-MON-YY')) >= p_on",
                "oracle_rows_where_they_disagree": o_pop[
                    "subscription_rows_where_the_two_predicates_disagree"
                ],
                "target_tenants_where_they_disagree": ent_pop[
                    "tenants_where_the_two_predicates_disagree"
                ],
            },
        )
    )

    # ACC-OUTER-JOIN: direction and null-extension preserved, with the measured population.
    checks.append(
        check(
            "ACC-OUTER-JOIN",
            {
                "subscriptions_kept_with_a_missing_plan": o_pop[
                    "subscriptions_with_a_missing_plan_row"
                ],
                "join_kept_every_subscription": True,
            },
            {
                "subscriptions_kept_with_a_missing_plan": chg["rows_with_a_missing_plan_row"],
                "join_kept_every_subscription": snap["counts"]["subscriptions"]
                == src["subscriptions"] + chg["requests"],
            },
            "p.id (+) = s.plan_id in fn_entitlement, evaluated by Oracle, vs the LEFT JOIN in the "
            "notebook — direction and null-extension both",
            null_extended_entitlement_rows={
                "oracle": sum(
                    1 for e in oracle["entitlements"].values() if e["plan_null_extended"]
                ),
                "target": ent_pop["plan_null_extended_rows"],
            },
            note="the population is zero on this seed and is reported as a measured zero, not as a "
            "demonstration; the direction is still proven by the row counts, since an inner join "
            "would have dropped rows",
        )
    )

    # ACC-ROWNUM: the pinned tie-break and the measured tie population.
    checks.append(
        check(
            "ACC-ROWNUM",
            {
                "tie_break": CONST["covering_pick_order_by"],
                "tenant_starts_on_groups_with_a_tie": o_pop["tenant_starts_on_groups_with_a_tie"],
            },
            {
                "tie_break": run2["anomaly_detections"]["ANOM-ROWNUM-TIEBREAK"][
                    "tie_break_pinned_to"
                ],
                "tenant_starts_on_groups_with_a_tie": ent_pop["rows_with_tied_starts_on"],
            },
            "the tie population measured on both sides, and the deterministic pick this port pinned "
            "for both ROWNUM sites",
            rows_with_more_than_one_candidate=ent_pop["rows_with_more_than_one_candidate"],
            note="measured, not asserted: both ROWNUM paths remain listed in unverified_paths "
            "because a tie would be decided by the source's plan, not by its text",
        )
    )

    # ACC-CANCELLED and the suspended flip, both measured on the close-out.
    checks.append(
        check(
            "ACC-CANCELLED",
            {
                "cancelled_visited": o_chg["cancelled_subscriptions_visited"],
                "cancelled_preserved": o_chg["cancelled_preserved"],
                "closeout_status_from_30": 30,
                "closeout_status_from_20": 10,
            },
            {
                "cancelled_visited": chg["cancelled_subscriptions_visited"],
                "cancelled_preserved": chg["cancelled_preserved"],
                "closeout_status_from_30": o_dialect["closeout_status_from_30"],
                "closeout_status_from_20": o_dialect["closeout_status_from_20"],
            },
            "DECODE(r.status_cd, 30, 30, 10) evaluated by Oracle, and the close-out population on "
            "both sides",
            suspended_to_active_flips={
                "oracle": o_chg["suspended_to_active_flips"],
                "target": chg["suspended_to_active_flips"],
            },
            note="no cancelled subscription is open on this seed, so the 30-stays-30 branch is "
            "measured at zero rows and proven on the expression instead (trg_sub_no_uncancel, "
            "D-16); the 20 → 10 flip is customer-visible, is reproduced rather than corrected, and "
            "its population is named",
        )
    )

    # The close-out itself, per row, plus the strict `<` population.
    checks.append(
        check(
            "CHANGE-PLAN-CLOSEOUT",
            {
                "subscriptions_closed": o_chg["subscriptions_closed_by_the_loop"],
                "new_subscriptions": o_chg["new_subscriptions"],
                "open_subscriptions_left_overlapping_by_the_strict_less_than": o_chg[
                    "open_subscriptions_left_overlapping_by_the_strict_less_than"
                ],
                "open_subscriptions_starting_exactly_on_the_effective_date": o_chg[
                    "open_subscriptions_starting_exactly_on_the_effective_date"
                ],
                "effective_on_minus_one_day": o_dialect["effective_on_minus_one_day"],
            },
            {
                "subscriptions_closed": chg["subscriptions_closed_by_the_loop"],
                "new_subscriptions": chg["new_subscriptions"],
                "open_subscriptions_left_overlapping_by_the_strict_less_than": chg[
                    "open_subscriptions_left_overlapping_by_the_strict_less_than"
                ],
                "open_subscriptions_starting_exactly_on_the_effective_date": chg[
                    "open_subscriptions_starting_exactly_on_the_effective_date"
                ],
                "effective_on_minus_one_day": sorted(
                    {
                        norm(r["ends_on"], "ts")
                        for r in snap["sub_rows"]
                        if norm(r["closed_by_change"], "flag")
                        and norm(r["change_effective_on"], "ts")
                        == f"{CHANGE_EFFECTIVE_ON} 00:00:00"
                    }
                )[0],
            },
            "the request population derived by the spec's rule, evaluated read-only by Oracle, vs "
            f"{CATALOG}.{SCHEMA}.subscriptions after the MERGE",
            requests=chg["requests"],
            requests_pinned_by_a_transcript=chg["requests_pinned_by_a_transcript"],
            closeout_order_pinned_to=chg["closeout_order_pinned_to"],
            time_component_carried_rows={
                "oracle": o_chg["closeout_ends_on_carrying_a_time_component"],
                "target": chg["closeout_ends_on_carrying_a_time_component"],
            },
            note="every seeded subscription starts at midnight, so the time-carrying population is "
            "a measured zero; the expression itself is proven against Oracle's own "
            "DATE-with-time arithmetic in the dialect probe",
            oracle_date_arithmetic_with_a_time_component=o_dialect[
                "effective_on_with_time_minus_one_day"
            ],
        )
    )

    # The request derivation itself: two independent derivations, one per engine.
    o_req = {
        (r["tenant_id"], r["effective_on"], r["plan_id"]) for r in oracle["change_requests"]
    }
    t_req = {
        (r["tenant_id"], r["effective_on"], r["plan_id"]) for r in run2["change_requests"]
    }
    checks.append(
        check(
            "CHANGE-REQUEST-DERIVATION",
            {"requests": len(o_req), "sets_identical": True},
            {"requests": len(t_req), "sets_identical": o_req == t_req},
            "the spec's derivation rule evaluated independently on Oracle and on bronze",
            rule=SPEC["change_requests"]["derivation"],
            only_in_oracle=sorted(o_req - t_req)[:10],
            only_in_target=sorted(t_req - o_req)[:10],
        )
    )

    # D-14 keys: the target's ids come from the same recipe as the source function's.
    o_keys = {(k["tenant_id"], k["effective_on"]): k["new_subscription_id"] for k in oracle["sample_keys"]}
    t_keys = {
        (r["tenant_id"], r["effective_on"]): r["new_subscription_id"]
        for r in run2["change_requests"]
    }
    key_diff = {k: {"oracle": v, "target": t_keys.get(k)} for k, v in o_keys.items() if t_keys.get(k) != v}
    checks.append(
        check(
            "ACC-MERGE-KEY",
            {"keys_compared": len(o_keys), "keys_differing": 0},
            {"keys_compared": len(o_keys), "keys_differing": len(key_diff)},
            "pkg_ow_util.f_md5_uuid(tenant || plan || TO_CHAR(effective_on,'YYYY-MM-DD')) evaluated "
            "by Oracle vs the target's own derivation of the same id (D-14)",
            differences=[{"key": list(k), **v} for k, v in list(key_diff.items())[:10]],
        )
    )

    # ACC-NS.
    checks.append(
        check(
            "ACC-NS",
            {
                "ns": ns,
                "rows_without_ns": {"plans": 0, "subscriptions": 0, "entitlements": 0},
                "volume_path": f"{LANDING_ROOT}/{ns}/{UNIT}",
            },
            {
                "ns": ns,
                "rows_without_ns": snap["rows_without_ns"],
                "volume_path": f"{LANDING_ROOT}/{ns}/{UNIT}",
            },
            f"{CATALOG}.{SCHEMA}.* for ns={ns}, and the run summary path the notebook wrote",
            rows_in_other_namespaces_left_untouched=snap["rows_in_other_ns"],
            merge_keys={t: TABLES[t]["merge_key"] for t in TABLES},
            job_parameter="ns",
        )
    )

    # ACC-IDEM: the second run's own commits, attributed by job run id and pre-run Delta version.
    idem_rows = {
        t: {
            "rows_inserted": m["rows_inserted"],
            "rows_updated": m["rows_updated"],
            "rows_deleted": m["rows_deleted"],
        }
        for t, m in run2["merge_metrics"].items()
    }
    zero = {"rows_inserted": 0, "rows_updated": 0, "rows_deleted": 0}
    checks.append(
        check(
            "ACC-IDEM",
            {t: zero for t in idem_rows},
            idem_rows,
            "DESCRIBE HISTORY on each target, restricted to commits newer than the target's "
            "pre-run version and written by the second run's own job.jobRunId",
            first_run={
                "batch_id": run1["batch_id"],
                "job_run_id": run1["run_id"],
                "merge_metrics": run1["merge_metrics"],
            },
            second_run={
                "batch_id": run2["batch_id"],
                "job_run_id": run2["run_id"],
                "attribution": next(iter(run2["merge_metrics"].values()))["attributed_by"],
                "pre_run_versions": {
                    t: m["pre_run_version"] for t, m in run2["merge_metrics"].items()
                },
            },
            target_counts_after_each_run={
                "first": run1["target_counts"],
                "second": run2["target_counts"],
            },
            # A pair of runs against targets that already hold the converged load both insert
            # nothing, which proves convergence but not that the insert path works. The commit
            # that did the cold load is read out of each target's Delta history so the insert
            # path is measured; it belongs to an earlier invocation when `is_this_run` is false.
            cold_load_commits=run2["cold_load_commits"],
        )
    )

    # The transcripts, one check each.
    checks.extend(transcript_checks(oracle, snap, pinned_sha))

    detected = sorted(k for k, v in run2["anomaly_detections"].items() if v["detected"])
    failed = [c["id"] for c in checks if c["result"] == "fail"]

    return {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": now_iso(),
        "run_mode": "live",
        "recon_result": "fail" if failed else "pass",
        "failed_checks": failed,
        "values_recomputed_from_target": True,
        "checks": checks,
        "source_provenance": {
            "artifact": SPEC["source_artifact_path"],
            "entrypoints": SPEC["source_entrypoints"],
            "oracle_source_sha": oracle["oracle_source_sha"],
            "pinned_sha_file": str(PINNED_SHA_FILE.relative_to(ROOT)),
            "oracle_banner": oracle["oracle_banner"],
            "seeded_scale": seeded_scale(),
            "live_source_counts": src,
            "bronze_inputs": SPEC["bronze_inputs"],
            "transcripts": sorted(p.name for p in TRANSCRIPT_DIR.glob("PLANS-*.json")),
            "postgres_transcripts_are_a_cross_check_not_the_baseline": True,
        },
        "runs": [
            {
                "batch_id": r["batch_id"],
                "job_run_id": r["run_id"],
                "run_page_path": r["run_page_path"],
                "entitlement_on": r["entitlement_on"],
                "change_effective_on": r["change_effective_on"],
                "quarantine_rate_pct": r["quarantine"]["rate_pct"],
                "merge_metrics": r["merge_metrics"],
                "target_counts": r["target_counts"],
            }
            for r in (run1, run2)
        ],
        "accounting": acc,
        "quarantine": quar,
        "money": {
            "target": snap["money"],
            "oracle": {
                "plans.monthly_fee_total": str(o_plan_money.quantize(decimal.Decimal("0.01"))),
                "entitlements.monthly_fee_total": str(
                    o_ent_money.quantize(decimal.Decimal("0.01"))
                ),
            },
            "quarantined_rows_alongside_every_figure": quar["physical_rows_this_run"],
            "money_column_types": {c: snap["column_types"].get(c) for c in MONEY_COLUMNS},
        },
        "measured_populations": {
            "unknown_tier_plans": {
                "oracle": sum(1 for p in oracle["all_plans"] if p["tier"] == "UNKNOWN"),
                "target": run2["plans_populations"]["unknown_tier_plans"],
                "note": "an unmapped or NULL tier_cd is the literal 'UNKNOWN', not a NULL and not a "
                "quarantine",
            },
            "inactive_plans_loaded_but_unlisted": {
                "oracle": sum(1 for p in oracle["all_plans"] if not p["listed_by_fn_list_plans"]),
                "target": run2["plans_populations"]["inactive_plans"],
            },
            "plans_with_a_null_active_yn": {
                "oracle": sum(1 for p in oracle["all_plans"] if p["active_yn"] is None),
                "target": run2["plans_populations"]["null_active_yn_plans"],
                "note": "NVL(active_yn,'N') = 'Y' makes a NULL active_yn inactive",
            },
            "null_extended_plan_joins": {
                "oracle": o_pop["subscriptions_with_a_missing_plan_row"],
                "target": chg["rows_with_a_missing_plan_row"],
            },
            "tied_starts_on": {
                "oracle": o_pop["tenant_starts_on_groups_with_a_tie"],
                "target": ent_pop["rows_with_tied_starts_on"],
            },
            "suspended_to_active_flips_on_closeout": {
                "oracle": o_chg["suspended_to_active_flips"],
                "target": chg["suspended_to_active_flips"],
            },
            "overlapping_subscriptions_from_the_strict_less_than": {
                "oracle": o_chg["open_subscriptions_left_overlapping_by_the_strict_less_than"],
                "target": chg["open_subscriptions_left_overlapping_by_the_strict_less_than"],
            },
            "tenants_that_would_hit_the_stale_globals_mismatch": {
                "oracle": sum(1 for w in oracle["global_walk"] if w["stale_global_mismatch"]),
                "oracle_tenants_whose_global_lookup_finds_nothing": sum(
                    1 for w in oracle["global_walk"] if not w["global_lookup_matched"]
                ),
                "target": ent_pop["tenants_that_would_hit_the_stale_globals_mismatch"],
                "target_entitlement_rows_carrying_a_mismatch": ent_pop[
                    "rows_carrying_a_stale_global_mismatch"
                ],
                "note": "every tenant on this seed has a covering subscription, so the mismatch "
                "population is a measured zero; the walk is still reconstructed and published as "
                "columns so a non-zero population would be visible",
            },
            "source_reapply_exposure": {
                "requests_whose_new_id_already_exists_in_the_source": o_chg[
                    "new_ids_already_present_in_the_source"
                ],
                "target_requests_whose_new_id_already_exists_in_bronze": chg[
                    "new_ids_already_present_in_the_source"
                ],
                "note": "the source's INSERT has no DUP_VAL_ON_INDEX handler, so re-applying a "
                "change closes the open subscriptions and then raises ORA-00001, leaving the "
                "close-outs applied and no new subscription. This port does not reproduce that "
                "partial-effect failure: it MERGEs on the D-14 id plus ns, and the second identical "
                "run changed nothing. The exposure is measured on the request population above and "
                "is a declared divergence, not parity.",
            },
        },
        "idempotency_rerun": {
            "performed": True,
            "result": "pass"
            if all(v == zero for v in idem_rows.values())
            else "fail",
            "evidence": "second identical run "
            f"(batch {run2['batch_id']}, job run {run2['run_id']}): "
            + json.dumps(idem_rows)
            + "; commits attributed by job.jobRunId and each target's pre-run Delta version "
            + json.dumps({t: m["pre_run_version"] for t, m in run2["merge_metrics"].items()}),
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": detected,
            "missing": [a for a in EXPECTED_ANOMALIES if a not in detected],
            "unexpected": [a for a in detected if a not in EXPECTED_ANOMALIES],
            "detail": run2["anomaly_detections"],
        },
        "unverified_paths": [
            "pkg_plans.sp_change_plan was NOT executed against the source: it mutates "
            "SUBSCRIPTIONS. Its close-out loop and its INSERT are re-expressed as read-only SELECTs "
            "and evaluated by Oracle, so the parity side is Oracle's own evaluation of the "
            "re-expression rather than the procedure's own effect. Transcripts PLANS-004/005 pin "
            "the end state the procedure produces, and both reproduce.",
            "ROWNUM = 1 in the package-global lookup has no ORDER BY at all, and ROWNUM <= 1 in the "
            "returned cursor orders only by starts_on DESC. Neither is a total order, so the "
            f"source's answer under a tie is decided by its plan. Both are pinned to {CONST['covering_pick_order_by']} "
            f"here; tenant/starts_on groups with a tie were measured at "
            f"{o_pop['tenant_starts_on_groups_with_a_tie']} on this seed, so no tie was exercised "
            "and neither path is claimed as parity.",
            "The row-by-row close-out (ANOM-ROWBYROW-CLOSEOUT) is re-expressed set-wise with the "
            f"order pinned to {CONST['closeout_order_by']}. Each row's new state depends only on its "
            "own old state, so the pinned order changes no value on this data; the source's "
            "order-dependence is in its shape and was not exercised.",
            "The suspended → active flip on close-out was exercised on "
            f"{o_chg['suspended_to_active_flips']} subscription(s). The cancelled-stays-cancelled "
            f"branch was visited by {o_chg['cancelled_subscriptions_visited']} rows: no cancelled "
            "subscription is open on this seed, so trg_sub_no_uncancel/D-16 is proven on the "
            "expression (DECODE evaluated by Oracle) and not on a loaded row.",
            "Populations measured at zero on this seed, reported as zero rather than as "
            "demonstrations: subscriptions whose plan row is missing (the outer join's "
            "null-extension), rows where fn_entitlement's two date predicates disagree, tenants "
            "with no covering subscription (so the stale package-global mismatch, whose walk is "
            "reconstructed but never triggered), close-out dates carrying a time component, and "
            "requests whose new id already exists in the source (the ORA-00001 re-apply exposure).",
            "NUMERIC_OVERFLOW is unreachable from this bronze slice, whose money columns are "
            "already DECIMAL(14,2). Reachability is shown by pushing synthetic pre-cast values "
            "through the load's own wider raw column, try_cast and guard: "
            + json.dumps(run2["overflow_probe"]["cases"]),
            "pkg_ow_util.log_msg writes BILLING_AUDIT_LOG in an autonomous transaction. Out of this "
            "unit's parity scope per D-20; it belongs to bronze_hist and is not reproduced.",
            "ow_tp.silver.subscriptions is also written by wave 4 (sp_suspend_overdue). This unit "
            "only MERGEs the identities it produces, issues no DELETE, INSERT OVERWRITE or "
            "table-wide statement, and introduces no cross-unit locking or publication protocol "
            "(D-28): a second writer's rows would be left untouched, which is asserted by "
            "construction and not exercised here.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = argv[argv.index("--ns") + 1] if "--ns" in argv else "demo"

    pinned_sha = PINNED_SHA_FILE.read_text().strip()
    computed_sha = oracle_truth.oracle_source_sha()
    if pinned_sha != computed_sha:
        raise Halt(
            f"pinned Oracle source SHA {pinned_sha} != checked-out tree {computed_sha}: stop and "
            "report, the transcripts no longer describe this source"
        )
    print(f"[sha] {computed_sha} matches {PINNED_SHA_FILE.name}")

    requests = oracle_truth.derive_requests(ENTITLEMENT_ON, CHANGE_EFFECTIVE_ON, OVERRIDES)
    oracle = oracle_truth.snapshot(ENTITLEMENT_ON, requests)
    print(
        f"[oracle] counts={oracle['source_counts']} entitlements={len(oracle['entitlements'])} "
        f"requests={len(requests)} closeouts={oracle['change_populations']['subscriptions_closed_by_the_loop']}"
    )

    dbx = Dbx()
    deploy(dbx)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    run1 = run_notebook(dbx, ns, f"{stamp}a")
    print(
        f"[run a] {run1['run_id']} quar={run1['quarantine']['rate_pct']}% "
        f"merge={json.dumps(run1['merge_metrics'])}"
    )
    if run1["quarantine"]["rate_pct"] > SPEC["quarantine_halt_threshold_pct"]:
        raise Halt(
            f"quarantine rate {run1['quarantine']['rate_pct']}% exceeds "
            f"{SPEC['quarantine_halt_threshold_pct']}% on the declared basis: halting the unit"
        )

    run2 = run_notebook(dbx, ns, f"{stamp}b")
    print(f"[run b] {run2['run_id']} merge={json.dumps(run2['merge_metrics'])}")
    if run2["quarantine"]["rate_pct"] > SPEC["quarantine_halt_threshold_pct"]:
        raise Halt(
            f"quarantine rate {run2['quarantine']['rate_pct']}% exceeds "
            f"{SPEC['quarantine_halt_threshold_pct']}% on the declared basis: halting the unit"
        )

    snap = target_snapshot(dbx, ns)

    # Rows this run rejected are excluded from parity by *this run's* batch, never by whatever the
    # ledger still carries (tolerance item 6).
    ledger = run2["quarantine"]["rejection_ledger"]
    rejected_plans = set(ledger["rejected_plan_ids_this_run"])
    rejected_subs = set(ledger["rejected_subscription_ids_this_run"])

    plan_diff = diff_rows(
        {p["id"]: p for p in oracle["all_plans"] if p["id"] not in rejected_plans},
        {p["id"]: p for p in snap["plan_rows"]},
        PLAN_COLS,
        "OW_BILLING.PLANS (every row; fn_list_plans' filter is carried as columns)",
    )
    ent_diff = diff_rows(
        oracle["entitlements"],
        {e["tenant_id"]: e for e in snap["ent_rows"]},
        ENT_COLS,
        f"fn_entitlement's returned cursor per tenant on {ENTITLEMENT_ON}",
    )
    sub_diff = diff_rows(
        {
            r["id"]: r
            for r in oracle["change_end_state"]
            if r["id"] not in rejected_subs
        },
        {r["id"]: r for r in snap["sub_rows"]},
        SUB_COLS,
        "the SUBSCRIPTIONS end state sp_change_plan would leave, re-expressed read-only",
    )
    print(
        f"[parity] plans differing={plan_diff['rows_differing']}/{plan_diff['rows_compared']} "
        f"entitlements differing={ent_diff['rows_differing']}/{ent_diff['rows_compared']} "
        f"subscriptions differing={sub_diff['rows_differing']}/{sub_diff['rows_compared']}"
    )

    report = build_report(
        ns, oracle, run1, run2, snap, plan_diff, ent_diff, sub_diff, pinned_sha
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(f"[recon] {report['recon_result']} -> {REPORT_PATH.relative_to(ROOT)}")
    if report["failed_checks"]:
        print(f"[recon] FAILED: {report['failed_checks']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
