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
from scripts.tp_databricks.silver_plans import edge_fixture, oracle_truth

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

# The generated scratch namespace: the paths this seed leaves at zero are exercised there against an
# independent Python model of 02_pkg_plans.sql, because seeding them in Oracle would mean mutating
# the source. Its provenance is stated in the report in plain words.
EDGE_NS = edge_fixture.NS
EDGE_ENT_COLS: dict[str, str] = {
    "subscription_id": "text",
    "plan_id": "text",
    "plan_code": "text",
    "tier": "text",
    "monthly_fee": "money",
    "included_units": "count",
    "status_cd": "code",
    "subscription_status": "text",
    "plan_null_extended": "flag",
    "candidate_rows": "code",
}


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


def run_notebook(
    dbx: Dbx, ns: str, batch_id: str, applied_requests: list[dict] | None = None
) -> dict[str, Any]:
    # `label` is what the notebook carries as the request's `pinned_by_transcript` column, so a
    # request pinned by a transcript reaches the run named by that transcript.
    declared = [
        {
            "tenant_id": r["tenant_id"],
            "plan_id": r["plan_id"],
            "effective_on": r["effective_on"],
            "label": r.get("label") or r.get("pinned_by_transcript"),
        }
        for r in applied_requests or []
    ]
    run_id = dbx.submit_notebook_run(
        run_name=f"ow_tp_silver_plans_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_plans",
        params={
            "applied_requests": json.dumps(declared) if declared else "",
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


def halt_if_over(run: dict[str, Any], label: str) -> None:
    """Every declared population is checked against the threshold, not just the driver."""
    bases = run["quarantine"]["halt_bases"]
    over = run["quarantine"]["populations_over_threshold"]
    if over:
        detail = "; ".join(
            f"{n}: {bases[n]['rejected_rows']} of {bases[n]['source_rows']} "
            f"({bases[n]['rate_pct']}%)"
            for n in over
        )
        raise Halt(
            f"{label}: {detail} exceeds {SPEC['quarantine_halt_threshold_pct']}% on its own paired "
            "numerator and denominator: halting the unit and reporting instead of loading around it"
        )


def first(values: list[Any]) -> Any:
    """The one value a population of one carries, or None when the population is empty."""
    return values[0] if values else None


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


# -- the generated scratch namespace ------------------------------------------

# The source-table labels the notebook stamps on each rejection population.
QUAR_SOURCE_PLANS = "OW_BILLING.PLANS"
QUAR_SOURCE_SUBS = "OW_BILLING.SUBSCRIPTIONS"
QUAR_SOURCE_REQ = "OW_BILLING.SUBSCRIPTIONS+PKG_PLANS.SP_CHANGE_PLAN(request)"
QUAR_SOURCE_ENT = "PKG_PLANS.FN_ENTITLEMENT(tenant)"


def edge_evidence(dbx: Dbx) -> dict[str, Any]:
    """Run the unit over the generated `plans_edge` fixture and check it against its own model.

    The fixture is generated, stated as generated, and lives only in `ns=plans_edge`: Oracle holds
    no copy of it, because seeding one would mean mutating the source. The declared side of this
    comparison is `edge_fixture.expectations()`, an independent Python re-expression of
    `02_pkg_plans.sql` written from the package text. This is also where the cold-load/no-op pair is
    produced with the final code: only rows this unit itself wrote in this generated namespace are
    removed first, and no other namespace is touched.
    """
    exp = edge_fixture.expectations()
    pop = exp["populations"]
    seeded = edge_fixture.seed_bronze(dbx)
    removed = edge_fixture.reset_targets(dbx)
    fixture_stamped = {
        f"{CATALOG}.{BRONZE}.{t}": int(
            dbx.sql(
                f"SELECT count(*) FROM {CATALOG}.{BRONZE}.{t} "
                f"WHERE ns = {sql_str(EDGE_NS)} AND _source_table = "
                f"{sql_str(edge_fixture.ORIGIN)}"
            )[0][0]
        )
        for t in ("plans", "tenants", "subscriptions")
    }

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    cold = run_notebook(dbx, EDGE_NS, f"{stamp}e1", edge_fixture.APPLIED_REQUESTS)
    halt_if_over(cold, f"ns={EDGE_NS} cold load")
    print(f"[edge cold] {cold['run_id']} merge={json.dumps(cold['merge_metrics'])}")
    noop = run_notebook(dbx, EDGE_NS, f"{stamp}e2", edge_fixture.APPLIED_REQUESTS)
    halt_if_over(noop, f"ns={EDGE_NS} re-run")
    print(f"[edge noop] {noop['run_id']} merge={json.dumps(noop['merge_metrics'])}")

    snap = target_snapshot(dbx, EDGE_NS)
    chg = noop["subscription_populations"]
    ent_pop = noop["entitlement_populations"]
    plans_pop = noop["plans_populations"]
    bases = noop["quarantine"]["halt_bases"]

    checks: list[dict[str, Any]] = []
    sot = (
        "the generated fixture in scripts/tp_databricks/silver_plans/edge_fixture.py and its "
        "independent Python model of 02_pkg_plans.sql (expectations()), vs the Delta targets for "
        f"ns={EDGE_NS} read back after the MERGE"
    )
    checks.append(
        check(
            "EDGE-FIXTURE-PROVENANCE",
            {
                **{f"{CATALOG}.{BRONZE}.{k.split('.')[-1]}": v for k, v in seeded.items()},
                "every_row_stamped_generated": True,
            },
            {
                **fixture_stamped,
                "every_row_stamped_generated": all(
                    fixture_stamped[k] == v for k, v in seeded.items()
                ),
            },
            f"count(*) over {CATALOG}.{BRONZE}.* for ns={EDGE_NS}, grouped by _source_table",
            provenance=edge_fixture.PROVENANCE,
            rows_removed_from_this_namespaces_targets_before_the_cold_load=removed,
            note="generated fixture activity, declared as such: nothing here is customer data, "
            "nothing here exists in OW_BILLING, and every row carries "
            f"_source_table = '{edge_fixture.ORIGIN}'",
        )
    )

    listed = sorted(
        (r for r in snap["plan_rows"] if norm(r["listed_by_fn_list_plans"], "flag")),
        key=lambda r: int(r["list_seq"]),
    )
    checks.append(
        check(
            "EDGE-FN-LIST-PLANS",
            [
                {
                    "code": p["code"],
                    "tier": p["tier"],
                    "monthly_fee": norm(p["monthly_fee"], "money"),
                }
                for p in exp["fn_list_plans"]
            ],
            [
                {
                    "code": r["code"],
                    "tier": r["tier"],
                    "monthly_fee": norm(r["monthly_fee"], "money"),
                }
                for r in listed
            ],
            sot,
            note="NVL(active_yn,'N') = 'Y' with ORDER BY monthly_fee, code, and the tier DECODE's "
            "'UNKNOWN' default on both a NULL and an unmapped tier_cd",
        )
    )
    checks.append(
        check(
            "EDGE-PLANS-POPULATIONS",
            {
                "source_rows": pop["plans_source_rows"],
                "unknown_tier_plans": pop["unknown_tier_plans"],
                "inactive_plans": pop["inactive_plans"],
                "null_active_yn_plans": pop["null_active_yn_plans"],
                "listed_by_fn_list_plans": pop["listed_by_fn_list_plans"],
            },
            {
                "source_rows": plans_pop["source_rows"],
                "unknown_tier_plans": plans_pop["unknown_tier_plans"],
                "inactive_plans": plans_pop["inactive_plans"],
                "null_active_yn_plans": plans_pop["null_active_yn_plans"],
                "listed_by_fn_list_plans": plans_pop["listed_by_fn_list_plans"],
            },
            sot,
        )
    )

    ent_diff = diff_rows(
        exp["entitlements"],
        {e["tenant_id"]: e for e in snap["ent_rows"]},
        EDGE_ENT_COLS,
        f"fn_entitlement's returned cursor per tenant on {ENTITLEMENT_ON}, modelled from the "
        "package text over the generated fixture",
    )
    checks.append(
        check(
            "EDGE-ENTITLEMENT-PARITY",
            {"rows_differing": 0, "rows_compared": ent_diff["oracle_rows"]},
            {
                "rows_differing": ent_diff["rows_differing"],
                "rows_compared": ent_diff["rows_compared"],
            },
            sot,
            **{k: v for k, v in ent_diff.items() if k in ("columns_compared", "differences")},
        )
    )
    sub_diff = diff_rows(
        exp["subscriptions_end_state"],
        {r["id"]: r for r in snap["sub_rows"]},
        SUB_COLS,
        "the SUBSCRIPTIONS end state sp_change_plan's close-out and INSERT imply for the generated "
        "fixture, modelled from the package text",
    )
    checks.append(
        check(
            "EDGE-SUBSCRIPTION-PARITY",
            {"rows_differing": 0, "rows_compared": sub_diff["oracle_rows"]},
            {
                "rows_differing": sub_diff["rows_differing"],
                "rows_compared": sub_diff["rows_compared"],
            },
            sot,
            **{k: v for k, v in sub_diff.items() if k in ("columns_compared", "differences")},
        )
    )

    checks.append(
        check(
            "EDGE-D18-SPLIT",
            {
                "rows_whose_plan_is_absent_from_the_source": pop[
                    "rows_whose_plan_is_absent_from_the_source"
                ],
                "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run": pop[
                    "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run"
                ],
                "plan_null_extended_entitlement_rows": pop["plan_null_extended_rows"],
                "entitlement_rows_not_produced_because_their_cursor_pick_was_rejected": pop[
                    "entitlement_rejected_rows"
                ],
            },
            {
                "rows_whose_plan_is_absent_from_the_source": chg[
                    "rows_whose_plan_is_absent_from_the_source"
                ],
                "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run": chg[
                    "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run"
                ],
                "plan_null_extended_entitlement_rows": ent_pop["plan_null_extended_rows"],
                "entitlement_rows_not_produced_because_their_cursor_pick_was_rejected": chg[
                    "entitlement_rows_not_produced_because_their_cursor_pick_was_rejected"
                ],
            },
            sot,
            note="D-18's null extension is presence in the *source* population: a subscription on a "
            "plan the source does not have is kept and null-extended, while a subscription on a "
            "plan this run rejected is itself rejected under FK_ORPHAN, and the entitlement its "
            "cursor would have returned is rejected with it rather than silently missing",
        )
    )

    checks.append(
        check(
            "EDGE-ANOMALY-POPULATIONS",
            {
                "rows_with_tied_starts_on": pop["rows_with_tied_starts_on"],
                "rows_with_more_than_one_candidate": pop["rows_with_more_than_one_candidate"],
                "tenants_with_no_covering_subscription_sentinel_predicate": pop[
                    "tenants_with_no_covering_subscription_sentinel_predicate"
                ],
                "subscriptions_closed_by_the_loop": pop["subscriptions_closed_by_the_loop"],
                "suspended_to_active_flips": pop["suspended_to_active_flips"],
                "cancelled_subscriptions_visited": pop["cancelled_subscriptions_visited"],
                "cancelled_preserved": pop["cancelled_preserved"],
                "open_subscriptions_left_overlapping_by_the_strict_less_than": pop[
                    "open_subscriptions_left_overlapping_by_the_strict_less_than"
                ],
                "new_ids_already_present_in_the_source": pop[
                    "new_ids_already_present_in_the_source"
                ],
                "new_subscriptions": pop["new_subscriptions"],
                "requests_rejected": pop["requests_rejected"],
            },
            {
                "rows_with_tied_starts_on": ent_pop["rows_with_tied_starts_on"],
                "rows_with_more_than_one_candidate": ent_pop["rows_with_more_than_one_candidate"],
                "tenants_with_no_covering_subscription_sentinel_predicate": ent_pop[
                    "tenants_with_no_covering_subscription_sentinel_predicate"
                ],
                "subscriptions_closed_by_the_loop": chg["subscriptions_closed_by_the_loop"],
                "suspended_to_active_flips": chg["suspended_to_active_flips"],
                "cancelled_subscriptions_visited": chg["cancelled_subscriptions_visited"],
                "cancelled_preserved": chg["cancelled_preserved"],
                "open_subscriptions_left_overlapping_by_the_strict_less_than": chg[
                    "open_subscriptions_left_overlapping_by_the_strict_less_than"
                ],
                "new_ids_already_present_in_the_source": chg[
                    "new_ids_already_present_in_the_source"
                ],
                "new_subscriptions": chg["new_subscriptions"],
                "requests_rejected": chg["requests_applied_by_this_run"]
                - chg["requests_accepted"],
            },
            sot,
            note="the populations the demo seed leaves at zero, exercised here: an unmapped and a "
            "NULL tier_cd, tied starts_on, an absent plan row, a plan rejected by this run, the "
            "strict-< overlap, a cancelled row visited by the close-out, a suspended row flipped "
            "to active, a tenant with no covering subscription after one that has it, and a "
            "request whose f_md5_uuid id already exists",
            entitlement_rows_carrying_a_stale_global_mismatch=ent_pop[
                "rows_carrying_a_stale_global_mismatch"
            ],
            tenants_carrying_a_stale_predecessor_plan_code_modelled=pop[
                "tenants_carrying_a_stale_predecessor_plan_code"
            ],
        )
    )

    checks.append(
        check(
            "EDGE-QUAR-HALT-BASES",
            {
                name: {"rate_pct": rate, "over_threshold": rate > float(SPEC[
                    "quarantine_halt_threshold_pct"
                ])}
                for name, rate in exp["halt_rates_pct"].items()
            },
            {
                name: {"rate_pct": b["rate_pct"], "over_threshold": b["over_threshold"]}
                for name, b in bases.items()
            },
            sot,
            paired_numerators_and_denominators={
                name: {
                    "rejected_rows": b["rejected_rows"],
                    "source_rows": b["source_rows"],
                    "basis": b["basis"],
                }
                for name, b in bases.items()
            },
            note="each declared population is evaluated on its own paired numerator and "
            "denominator, and this namespace makes all three non-zero",
        )
    )

    expected_quar: dict[str, int] = {}

    def bump(source_table: str, reason: str, rows: int = 1) -> None:
        expected_quar[f"{source_table}|{reason}"] = (
            expected_quar.get(f"{source_table}|{reason}", 0) + rows
        )

    for reason in exp["quarantine_reasons"]["plans"].values():
        bump(QUAR_SOURCE_PLANS, reason)
    for reason in exp["quarantine_reasons"]["subscriptions"].values():
        bump(QUAR_SOURCE_SUBS, reason)
    for reason in exp["quarantine_reasons"]["requests"].values():
        bump(QUAR_SOURCE_REQ, reason)
    if pop["entitlement_rejected_rows"]:
        bump(QUAR_SOURCE_ENT, "FK_ORPHAN", pop["entitlement_rejected_rows"])
    actual_quar: dict[str, int] = {}
    for row in snap["quarantine_rows"]:
        key = f"{row['source_table']}|{row['quarantine_reason']}"
        actual_quar[key] = actual_quar.get(key, 0) + row["rows"]
    checks.append(
        check(
            "EDGE-QUAR-PHYSICAL",
            expected_quar,
            actual_quar,
            f"count(*) over {CATALOG}.{SCHEMA}.quarantine_{UNIT} for ns={EDGE_NS}, grouped by "
            "source table and reason",
            closed_reason_set=SPEC["quarantine_reasons"],
            persisted_before_halt_decision=noop["quarantine"]["persisted_before_halt_decision"],
            note="every rejection is a physical row with its namespace, source table, source key, "
            "raw payload, detail, dictionary reference, batch id and exactly one closed reason - "
            "including the entitlements a rejected cursor pick removed",
        )
    )

    cold_rows = {
        t: {
            "rows_inserted": m["rows_inserted"],
            "rows_updated": m["rows_updated"],
            "rows_deleted": m["rows_deleted"],
        }
        for t, m in cold["merge_metrics"].items()
    }
    noop_rows = {
        t: {
            "rows_inserted": m["rows_inserted"],
            "rows_updated": m["rows_updated"],
            "rows_deleted": m["rows_deleted"],
        }
        for t, m in noop["merge_metrics"].items()
    }
    zero = {"rows_inserted": 0, "rows_updated": 0, "rows_deleted": 0}
    checks.append(
        check(
            "EDGE-COLD-LOAD-AND-NOOP",
            {
                "cold_load_inserted_rows_into_every_target": True,
                "second_identical_run": {t: zero for t in noop_rows},
            },
            {
                "cold_load_inserted_rows_into_every_target": all(
                    v["rows_inserted"] > 0 for v in cold_rows.values()
                ),
                "second_identical_run": noop_rows,
            },
            "DESCRIBE HISTORY on each target, restricted to commits newer than that target's "
            "pre-run Delta version and written by that run's own job.jobRunId",
            cold_load={
                "batch_id": cold["batch_id"],
                "job_run_id": cold["run_id"],
                "pre_run_versions": {
                    t: m["pre_run_version"] for t, m in cold["merge_metrics"].items()
                },
                "attribution": next(iter(cold["merge_metrics"].values()))["attributed_by"],
                "merge_metrics": cold_rows,
                "target_counts": cold["target_counts"],
            },
            no_op_run={
                "batch_id": noop["batch_id"],
                "job_run_id": noop["run_id"],
                "pre_run_versions": {
                    t: m["pre_run_version"] for t, m in noop["merge_metrics"].items()
                },
                "attribution": next(iter(noop["merge_metrics"].values()))["attributed_by"],
                "merge_metrics": noop_rows,
                "target_counts": noop["target_counts"],
            },
            rows_removed_first=removed,
            note="the pair is produced with the code in this revision, in the generated namespace: "
            "the cold load is a real insert into empty targets and the second identical run "
            "changed nothing. Only rows this unit wrote in ns=plans_edge were removed first; no "
            "row in any other namespace was deleted",
        )
    )

    return {
        "namespace": EDGE_NS,
        "checks": checks,
        "provenance": edge_fixture.PROVENANCE,
        "model": "scripts/tp_databricks/silver_plans/edge_fixture.py: expectations()",
        "requests_applied": edge_fixture.APPLIED_REQUESTS,
        "modelled_populations": pop,
        "target_counts": snap["counts"],
        "accounting": noop["accounting"],
        "quarantine": noop["quarantine"],
        "measured_populations": {
            "plans": plans_pop,
            "subscriptions": chg,
            "entitlements": ent_pop,
        },
        "anomaly_detections": noop["anomaly_detections"],
        "money": snap["money"],
        "cold_load": {
            "batch_id": cold["batch_id"],
            "job_run_id": cold["run_id"],
            "run_page_path": cold["run_page_path"],
            "merge_metrics": cold_rows,
        },
        "no_op_rerun": {
            "batch_id": noop["batch_id"],
            "job_run_id": noop["run_id"],
            "run_page_path": noop["run_page_path"],
            "merge_metrics": noop_rows,
            "result": "pass" if all(v == zero for v in noop_rows.values()) else "fail",
        },
        "shared_writer": noop["shared_writer"],
    }


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
    edge: dict,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    src = oracle["source_counts"]
    acc = run2["accounting"]
    quar = run2["quarantine"]
    ent_pop = run2["entitlement_populations"]
    chg = run2["subscription_populations"]
    o_chg = oracle["change_populations"]
    o_pop = oracle["populations"]
    edge_pop = edge["modelled_populations"]

    # The row-count asymmetry the applied-request policy leaves between source and target, declared
    # rather than closed by writing the derived population.
    unwritten = chg["derived_but_not_applied"]
    asymmetry = {
        "source_subscription_rows": src["subscriptions"],
        "target_subscription_rows": snap["counts"]["subscriptions"],
        "new_rows_from_applied_requests": o_chg["new_subscriptions"],
        "rows_the_unwritten_derived_requests_would_have_added": unwritten[
            "new_subscriptions_they_would_have_inserted"
        ],
        "rows_the_unwritten_derived_requests_would_have_closed": unwritten[
            "open_subscriptions_they_would_have_closed"
        ],
        "explanation": "the target carries one row per source subscription plus one per applied "
        "request that created a new identity. The derived population beyond the applied policy is "
        "measured and written nowhere, so the source and the target differ by exactly the applied "
        "requests' new identities and by nothing else.",
    }

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
                "subscriptions": acc["subscriptions"]["source_rows"]
                - chg["requests_applied_by_this_run"],
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
    # Every declared population is thresholded on its own paired numerator and denominator: a
    # PLANS or entitlements epidemic cannot report green behind the subscription driver's rate.
    checks.append(
        check(
            "ACC-QUAR-HALT-BASIS",
            {
                "threshold_pct": SPEC["quarantine_halt_threshold_pct"],
                "populations_evaluated": sorted(SPEC["quarantine_halt_bases"]),
                "populations_over_threshold": [],
            },
            {
                "threshold_pct": quar["halt_threshold_pct"],
                "populations_evaluated": sorted(quar["halt_bases"]),
                "populations_over_threshold": quar["populations_over_threshold"],
            },
            "each declared population, numerator and denominator on that one population, evaluated "
            "independently and halted on individually",
            halt_bases=quar["halt_bases"],
            worst_rate_pct=quar["worst_rate_pct"],
            physical_quarantine_rows=quar["physical_rows_this_run"],
            by_source_table_and_reason=quar["by_source_table_and_reason"],
            quarantine_persisted_before_the_halt_was_evaluated=quar[
                "persisted_before_halt_decision"
            ],
            closed_reason_set=SPEC["quarantine_reasons"],
            note="tolerance item 5 forbids diluting one population across the three physical "
            "tables; it does not license leaving two of them unthresholded, so each is checked on "
            f"its own and any one over {SPEC['quarantine_halt_threshold_pct']}% halts the unit. "
            f"ns={edge['namespace']} carries a non-zero rate on all three (see EDGE-QUAR-HALT-BASES)",
        )
    )

    # Target row counts, recomputed from Delta against the source population.
    checks.append(
        check(
            "TGT-COUNTS",
            {
                "plans": src["plans"],
                "subscriptions": src["subscriptions"] + o_chg["new_subscriptions"],
                "entitlements": acc["entitlements"]["source_rows"],
            },
            {
                "plans": snap["counts"]["plans"],
                "subscriptions": snap["counts"]["subscriptions"],
                "entitlements": len(snap["ent_rows"]),
            },
            f"count(*) over {CATALOG}.{SCHEMA}.* for ns={ns}, read back from Delta",
            quarantine_rows=snap["counts"][f"quarantine_{UNIT}"],
            source_target_row_count_asymmetry=asymmetry,
        )
    )

    # The asymmetry the applied-request policy leaves behind, declared rather than closed.
    checks.append(
        check(
            "CHANGE-REQUEST-APPLICATION-POLICY",
            {
                "requests_applied": len(oracle["change_requests"]),
                "every_applied_request_is_pinned_by_a_transcript": True,
                "derived_but_unwritten_requests": len(
                    oracle["change_requests_derived_but_not_applied"]
                ),
            },
            {
                "requests_applied": chg["requests_applied_by_this_run"],
                "every_applied_request_is_pinned_by_a_transcript": (
                    chg["requests_pinned_by_a_transcript"] == chg["requests_accepted"]
                ),
                "derived_but_unwritten_requests": chg["derived_but_not_applied"]["requests"],
            },
            "the spec's application policy: in a namespace holding migrated source data only the "
            "transcript-pinned requests are applied, and the rest of the derived population is "
            "measured and written nowhere",
            policy=chg["request_application_policy"],
            source_target_row_count_asymmetry=asymmetry,
            derived_but_unwritten=chg["derived_but_not_applied"],
            derived_but_unwritten_evaluated_on_oracle=o_chg["derived_but_not_applied"],
            note="applying the derived population would put plan-change events the source never "
            "had into a table waves 4 and 5 read next, so it is not written: every subscription "
            "that no transcript pins keeps its migrated source state",
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
            quarantine_rate_pct_per_declared_population={
                name: b["rate_pct"] for name, b in quar["halt_bases"].items()
            },
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
                "subscriptions_kept_with_a_missing_plan": chg[
                    "rows_whose_plan_is_absent_from_the_source"
                ],
                "join_kept_every_subscription": snap["counts"]["subscriptions"]
                == src["subscriptions"] + o_chg["new_subscriptions"],
            },
            "p.id (+) = s.plan_id in fn_entitlement, evaluated by Oracle, vs the LEFT JOIN in the "
            "notebook — direction and null-extension both",
            null_extended_entitlement_rows={
                "oracle": sum(
                    1 for e in oracle["entitlements"].values() if e["plan_null_extended"]
                ),
                "target": ent_pop["plan_null_extended_rows"],
            },
            rows_on_a_plan_present_in_the_source_but_rejected_by_this_run=chg[
                "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run"
            ],
            entitlement_rows_not_produced_because_their_cursor_pick_was_rejected=chg[
                "entitlement_rows_not_produced_because_their_cursor_pick_was_rejected"
            ],
            note="D-18's null extension is measured against presence in the *source* population: a "
            "plan this run rejected is not the source's missing plan, so its dependent "
            "subscriptions and entitlements are rejected under FK_ORPHAN and counted separately "
            "rather than null-extended into this count. Both populations are zero on this seed and "
            f"non-zero in ns={edge['namespace']} (see EDGE-D18-SPLIT); the direction is still "
            "proven by the row counts, since an inner join would have dropped rows",
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
                "effective_on_minus_one_day": first(
                    sorted(
                        {
                            norm(r["ends_on"], "ts")
                            for r in snap["sub_rows"]
                            if norm(r["closed_by_change"], "flag")
                            and norm(r["change_effective_on"], "ts")
                            == f"{CHANGE_EFFECTIVE_ON} 00:00:00"
                        }
                    )
                ),
            },
            "the request population derived by the spec's rule, evaluated read-only by Oracle, vs "
            f"{CATALOG}.{SCHEMA}.subscriptions after the MERGE",
            requests=chg["requests_applied_by_this_run"],
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
            # A pair of runs against ns=demo's already-converged targets both insert nothing, which
            # proves convergence but not that the insert path works. The insert path is proven by
            # the cold-load/no-op pair produced with this revision's code in the generated
            # namespace (EDGE-COLD-LOAD-AND-NOOP); the commits below are read out of each target's
            # Delta history and are labelled with whose run they belong to.
            cold_load_commits=run2["cold_load_commits"],
            cold_load_with_this_revisions_code=edge["cold_load"],
            note=f"ns={ns} was already converged, so the insert path is demonstrated in "
            f"ns={edge['namespace']} instead of asserted here",
        )
    )

    # The transcripts, one check each.
    checks.extend(transcript_checks(oracle, snap, pinned_sha))

    # The generated scratch namespace, reported separately from ns=demo's numbers.
    checks.extend(edge["checks"])

    detected = sorted(
        k
        for k in run2["anomaly_detections"]
        if run2["anomaly_detections"][k]["detected"]
        or edge["anomaly_detections"][k]["detected"]
    )
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
                "quarantine_halt_bases": r["quarantine"]["halt_bases"],
                "quarantine_populations_over_threshold": r["quarantine"][
                    "populations_over_threshold"
                ],
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
                "edge_namespace": edge["measured_populations"]["plans"]["unknown_tier_plans"],
                "note": "an unmapped or NULL tier_cd is the literal 'UNKNOWN', not a NULL and not a "
                "quarantine; zero on this seed, exercised on both an unmapped and a NULL tier_cd "
                f"in ns={edge['namespace']}",
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
                "target": chg["rows_whose_plan_is_absent_from_the_source"],
                "target_rows_on_a_plan_this_run_rejected_instead": chg[
                    "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run"
                ],
                "edge_namespace": {
                    "absent_from_the_source": edge["measured_populations"]["subscriptions"][
                        "rows_whose_plan_is_absent_from_the_source"
                    ],
                    "present_in_the_source_but_rejected_by_this_run": edge[
                        "measured_populations"
                    ]["subscriptions"][
                        "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run"
                    ],
                },
            },
            "tied_starts_on": {
                "oracle": o_pop["tenant_starts_on_groups_with_a_tie"],
                "target": ent_pop["rows_with_tied_starts_on"],
                "edge_namespace": edge["measured_populations"]["entitlements"][
                    "rows_with_tied_starts_on"
                ],
            },
            "suspended_to_active_flips_on_closeout": {
                "oracle": o_chg["suspended_to_active_flips"],
                "target": chg["suspended_to_active_flips"],
                "edge_namespace": edge["measured_populations"]["subscriptions"][
                    "suspended_to_active_flips"
                ],
            },
            "cancelled_subscriptions_visited_by_the_closeout": {
                "oracle": o_chg["cancelled_subscriptions_visited"],
                "target": chg["cancelled_subscriptions_visited"],
                "edge_namespace": edge["measured_populations"]["subscriptions"][
                    "cancelled_subscriptions_visited"
                ],
                "edge_namespace_cancelled_preserved": edge["measured_populations"][
                    "subscriptions"
                ]["cancelled_preserved"],
            },
            "overlapping_subscriptions_from_the_strict_less_than": {
                "oracle": o_chg["open_subscriptions_left_overlapping_by_the_strict_less_than"],
                "target": chg["open_subscriptions_left_overlapping_by_the_strict_less_than"],
                "edge_namespace": edge["measured_populations"]["subscriptions"][
                    "open_subscriptions_left_overlapping_by_the_strict_less_than"
                ],
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
                "edge_namespace_tenants_with_no_covering_subscription": edge[
                    "measured_populations"
                ]["entitlements"][
                    "tenants_with_no_covering_subscription_sentinel_predicate"
                ],
                "edge_namespace_tenants_carrying_a_stale_predecessor_plan_code": edge[
                    "modelled_populations"
                ]["tenants_carrying_a_stale_predecessor_plan_code"],
                "note": "every tenant on this seed has a covering subscription, so the mismatch "
                f"population is a measured zero here; ns={edge['namespace']} orders a tenant with "
                "no covering subscription immediately after one that has it, which is the pair "
                "g_last_tenant_id/g_last_plan_code goes stale on",
            },
            "source_reapply_exposure": {
                "requests_whose_new_id_already_exists_in_the_source": o_chg[
                    "new_ids_already_present_in_the_source"
                ],
                "target_requests_whose_new_id_already_exists_in_bronze": chg[
                    "new_ids_already_present_in_the_source"
                ],
                "edge_namespace_requests_whose_new_id_already_exists": edge[
                    "measured_populations"
                ]["subscriptions"]["new_ids_already_present_in_the_source"],
                "edge_namespace_inserts_suppressed_by_an_existing_identity": edge[
                    "measured_populations"
                ]["subscriptions"]["inserts_suppressed_by_an_existing_identity"],
                "note": "the source's INSERT has no DUP_VAL_ON_INDEX handler, so re-applying a "
                "change closes the open subscriptions and then raises ORA-00001, leaving the "
                "close-outs applied and no new subscription. This port does not reproduce that "
                "partial-effect failure: it MERGEs on the D-14 id plus ns, and the second identical "
                "run changed nothing. The exposure is measured on the request population above and "
                "is a declared divergence, not parity.",
            },
        },
        "change_requests": {
            "application_policy": chg["request_application_policy"],
            "derivation_rule": SPEC["change_requests"]["derivation"],
            "applied": oracle["change_requests"],
            "derived": len(oracle["change_requests_derived"]),
            "derived_but_unwritten": {
                "requests": oracle["change_requests_derived_but_not_applied"],
                "measured_on_oracle": o_chg["derived_but_not_applied"],
                "measured_on_the_target": chg["derived_but_not_applied"],
            },
            "source_target_row_count_asymmetry": asymmetry,
        },
        "namespace_evidence": {
            ns: {
                "kind": "migrated source data, compared against live Oracle",
                "target_counts": snap["counts"],
                "accounting": acc,
                "quarantine": quar,
                "requests_applied": len(oracle["change_requests"]),
                "requests_derived_but_unwritten": len(
                    oracle["change_requests_derived_but_not_applied"]
                ),
                # The earlier revision applied the whole derived population here. Narrowing the
                # policy leaves this unit's own generated subscriptions behind, so the run retracts
                # them by id — its own rows, its own origin, never table-wide, never another
                # writer's (D-28).
                "rows_this_unit_had_generated_here_and_has_now_retracted": run1[
                    "retraction_of_this_units_own_generated_rows"
                ],
            },
            edge["namespace"]: {
                "kind": "generated fixture, declared as generated: no customer data, no "
                "OW_BILLING row, and nothing pre-existing",
                "provenance": edge["provenance"],
                "declared_side_of_the_comparison": edge["model"],
                "requests_applied": edge["requests_applied"],
                "target_counts": edge["target_counts"],
                "accounting": edge["accounting"],
                "quarantine": edge["quarantine"],
                "measured_populations": edge["measured_populations"],
                "modelled_populations": edge["modelled_populations"],
                "money": edge["money"],
                "shared_writer": edge["shared_writer"],
                "cold_load": edge["cold_load"],
                "no_op_rerun": edge["no_op_rerun"],
                "anomaly_detections": edge["anomaly_detections"],
            },
        },
        "idempotency_rerun": {
            "performed": True,
            "result": "pass"
            if all(v == zero for v in idem_rows.values())
            and edge["no_op_rerun"]["result"] == "pass"
            else "fail",
            "evidence": f"ns={ns}: second identical run "
            f"(batch {run2['batch_id']}, job run {run2['run_id']}): "
            + json.dumps(idem_rows)
            + "; commits attributed by job.jobRunId and each target's pre-run Delta version "
            + json.dumps({t: m["pre_run_version"] for t, m in run2["merge_metrics"].items()})
            + f". ns={edge['namespace']} with this revision's code: cold load "
            f"(batch {edge['cold_load']['batch_id']}, job run "
            f"{edge['cold_load']['job_run_id']}) "
            + json.dumps(edge["cold_load"]["merge_metrics"])
            + f", then the identical re-run (batch {edge['no_op_rerun']['batch_id']}, job run "
            f"{edge['no_op_rerun']['job_run_id']}) "
            + json.dumps(edge["no_op_rerun"]["merge_metrics"]),
            "cold_load_and_no_op_pair": {
                "namespace": edge["namespace"],
                "cold_load": edge["cold_load"],
                "no_op_rerun": edge["no_op_rerun"],
            },
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": detected,
            "missing": [a for a in EXPECTED_ANOMALIES if a not in detected],
            "unexpected": [a for a in detected if a not in EXPECTED_ANOMALIES],
            "detail_by_namespace": {
                ns: run2["anomaly_detections"],
                edge["namespace"]: edge["anomaly_detections"],
            },
        },
        "unverified_paths": [
            f"The paths the ns={ns} seed leaves at zero are exercised in "
            f"ns={edge['namespace']} instead, on generated data declared as generated: "
            + json.dumps(
                {
                    k: edge_pop[k]
                    for k in (
                        "unknown_tier_plans",
                        "rows_with_tied_starts_on",
                        "rows_whose_plan_is_absent_from_the_source",
                        "rows_on_a_plan_present_in_the_source_but_rejected_by_this_run",
                        "open_subscriptions_left_overlapping_by_the_strict_less_than",
                        "cancelled_subscriptions_visited",
                        "suspended_to_active_flips",
                        "tenants_carrying_a_stale_predecessor_plan_code",
                        "new_ids_already_present_in_the_source",
                    )
                }
            )
            + ". They are not claimed as ns=demo findings and not claimed as Oracle activity.",
            "pkg_plans.sp_change_plan was NOT executed against the source: it mutates "
            "SUBSCRIPTIONS. Its close-out loop and its INSERT are re-expressed as read-only SELECTs "
            "and evaluated by Oracle, so the parity side is Oracle's own evaluation of the "
            "re-expression rather than the procedure's own effect. Transcripts PLANS-004/005 pin "
            "the end state the procedure produces, and both reproduce.",
            "ROWNUM = 1 in the package-global lookup has no ORDER BY at all, and ROWNUM <= 1 in the "
            "returned cursor orders only by starts_on DESC. Neither is a total order, so under a "
            "tie the source's own answer is decided by its plan and cannot be derived from the "
            f"text. Both are pinned to {CONST['covering_pick_order_by']} here. Ties were measured "
            f"at {o_pop['tenant_starts_on_groups_with_a_tie']} on the ns={ns} seed and at "
            f"{edge_pop['rows_with_tied_starts_on']} in ns={edge['namespace']}, where the pinned "
            "tie-break is shown to pick deterministically; what stays unverified is only *which* "
            "of the tied rows the source itself would return, which no read of the package can "
            "settle.",
            "The row-by-row close-out (ANOM-ROWBYROW-CLOSEOUT) is re-expressed set-wise with the "
            f"order pinned to {CONST['closeout_order_by']}. Each row's new state depends only on "
            "its own old state, so no pinned order changes a value on either namespace's data: "
            "the source's order-dependence is in its shape, and a data shape that makes two "
            "orders disagree does not exist under a single request per tenant.",
            "Populations still measured at zero rather than demonstrated: close-out dates "
            "carrying a time component (both namespaces' starts_on/ends_on are midnight, so "
            "D-07/T7's time carry is exercised by the expression and not by a row), and rows "
            "where fn_entitlement's two date predicates disagree (the sentinel predicate and the "
            "cursor predicate differ only for a row with ends_on in the future beyond 2099, which "
            "neither namespace contains).",
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

    # The derived population is measured in full; only the requests a transcript pins are applied to
    # a namespace holding migrated source data.
    derived = oracle_truth.derive_requests(ENTITLEMENT_ON, CHANGE_EFFECTIVE_ON, OVERRIDES)
    applied = oracle_truth.pinned_requests(derived)
    oracle = oracle_truth.snapshot(ENTITLEMENT_ON, applied, derived_requests=derived)
    print(
        f"[oracle] counts={oracle['source_counts']} entitlements={len(oracle['entitlements'])} "
        f"requests derived={len(derived)} applied={len(applied)} "
        f"unwritten={len(oracle['change_requests_derived_but_not_applied'])} "
        f"closeouts={oracle['change_populations']['subscriptions_closed_by_the_loop']}"
    )

    dbx = Dbx()
    deploy(dbx)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    run1 = run_notebook(dbx, ns, f"{stamp}a", applied)
    print(
        f"[run a] {run1['run_id']} quar={json.dumps(run1['quarantine']['halt_bases'])} "
        f"merge={json.dumps(run1['merge_metrics'])}"
    )
    halt_if_over(run1, f"ns={ns} first run")

    run2 = run_notebook(dbx, ns, f"{stamp}b", applied)
    print(f"[run b] {run2['run_id']} merge={json.dumps(run2['merge_metrics'])}")
    halt_if_over(run2, f"ns={ns} second run")

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

    # The generated scratch namespace: the wider procedure evidence, and the cold/no-op pair.
    edge = edge_evidence(dbx)

    report = build_report(
        ns, oracle, run1, run2, snap, plan_diff, ent_diff, sub_diff, pinned_sha, edge
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
