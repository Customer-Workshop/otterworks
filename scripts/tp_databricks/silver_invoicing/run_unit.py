"""Run the silver_invoicing unit against live Oracle and the shared workspace, and measure the recon.

Sequence, once per invocation:

1. verify the pinned Oracle source SHA (stop if it moved),
2. snapshot the source read-only: counts, the invoice **Oracle itself computes** for the population,
   the burn-down its sequence would perform, and its own INVOICES/INVOICE_LINES/CREDIT_NOTES rows,
3. deploy the notebook and its column spec under the parent-owned notebook root,
4. run the notebook twice on serverless with identical inputs,
5. recompute counts, money, types, checksums and every invoice row **from the Delta targets** over
   the SQL warehouse, independently of what the notebook reported,
6. compare against Oracle row by row and against the six pinned Oracle transcripts one by one,
7. write the recon report.

Nothing here writes to Oracle, to `ow_tp.bronze.*`, or to any table this unit does not own, and no
compute resource is ever created: the notebook runs on serverless and the recon SQL goes to the
pre-existing warehouse.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import sys
from typing import Any

from scripts.tp_databricks.bronze_core.dbx_client import Dbx, DbxError, sql_str
from scripts.tp_databricks.silver_invoicing import oracle_truth

ROOT = pathlib.Path(__file__).resolve().parents[3]
UNIT = "silver_invoicing"
CATALOG = "ow_tp"
SCHEMA = "silver"
BRONZE = "bronze"
NOTEBOOK_ROOT = "/Shared/ow_tp"
LANDING_ROOT = "/Volumes/ow_tp/bronze/landing"
NOTEBOOK_LOCAL = ROOT / "databricks" / "notebooks" / "ow_tp_silver_invoicing.py"
SPEC_LOCAL = ROOT / "databricks" / "ddl" / "silver_invoicing_spec.json"
REPORT_PATH = ROOT / "docs" / "tech-partnerships" / "recon" / f"{UNIT}.recon.json"
TRANSCRIPT_DIR = ROOT / "procs" / "oracle" / "transcripts" / "invoicing"
PINNED_SHA_FILE = ROOT / "procs" / "oracle" / "transcripts" / "ORACLE_SOURCE_SHA"
SEED_MANIFEST = ROOT / "testdata" / "legacy" / "manifests"

PERIOD_START = "2026-02-01"
PERIOD_END = "2026-02-28"

SPEC = json.loads(SPEC_LOCAL.read_text())
TABLES = {t["target"]: t for t in SPEC["tables"]}
COLUMN_CLASS = {
    f"{t['target']}.{c['name']}": c["class"] for t in SPEC["tables"] for c in t["columns"]
}

# The invoice columns compared against live Oracle, and the class each is normalised in. Money to the
# cent (T1/T11), counts as integers, the unrounded tax carriers at their pinned scale.
PARITY_COLS: dict[str, str] = {
    "period_id": "text",
    "plan_code": "text",
    "plan_fee": "money",
    "overage_amount": "money",
    "tax_exempt_yn": "text",
    "tax_computed": "money_unrounded",
    "tax_half": "money_unrounded",
    "charge_cap": "money",
    "credit_offered": "money",
    "credit_applied": "money",
    "subtotal": "money",
    "tax": "money",
    "total": "money",
    "overage_rate": "rate",
    "used_units": "count",
    "quota_units": "count",
    "computed_rollover_units": "count",
    "billable_units": "count",
    "first_tier_units": "count",
    "second_tier_units": "count",
    "suspension_prorated": "flag",
    "rating_subscription_id": "text",
    "fee_subscription_id": "text",
}
BURN_COLS: dict[str, str] = {
    "seq_no": "code",
    "issued_on": "text",
    "remaining_before": "money",
    "credit_running_before": "money",
    "applied_amount": "money",
    "remaining_after": "money",
    "credit_running_after": "money",
    "skipped_by_exit_when": "flag",
}
MIGRATED_COLS: dict[str, str] = {
    "tenant_id": "text",
    "period_id": "text",
    "issued_at": "text",
    "subtotal": "money",
    "tax": "money",
    "total": "money",
    "status_cd": "code",
}

EXPECTED_ANOMALIES = [
    "ANOM-GLOBAL-DEPENDENCY",
    "ANOM-HARDCODED-TAX",
    "ANOM-HALF-CENT-TAX",
    "ANOM-CREDIT-OVERAPPLY",
    "ANOM-DYNAMIC-SQL",
]

# Three synthetic bases for the tax-halves probe, evaluated by both engines. 54.56 is the value the
# pinned transcripts price; the other two are chosen to land the half on a half-cent.
TAX_PROBE_AMOUNTS = ["54.56", "100.00", "121.21"]


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
    "money_unrounded": decimal.Decimal("0.0000000001"),
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
    return value


# -- deploy / run --------------------------------------------------------------


def deploy(dbx: Dbx) -> None:
    dbx.mkdirs_workspace(NOTEBOOK_ROOT)
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/ow_tp_silver_invoicing",
        str(NOTEBOOK_LOCAL),
        fmt="SOURCE",
        language="PYTHON",
    )
    dbx.import_workspace(f"{NOTEBOOK_ROOT}/silver_invoicing_spec.json", str(SPEC_LOCAL), fmt="AUTO")


def run_notebook(dbx: Dbx, ns: str, batch_id: str) -> dict[str, Any]:
    run_id = dbx.submit_notebook_run(
        run_name=f"ow_tp_silver_invoicing_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_invoicing",
        params={
            "ns": ns,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "bronze_schema": BRONZE,
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
            "landing_root": LANDING_ROOT,
            "spec_path": f"{NOTEBOOK_ROOT}/silver_invoicing_spec.json",
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
            f"silver_invoicing notebook run {run_id} ended {state}: "
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
    ns_lit = sql_str(ns)
    counts = {}
    for name in ("invoices", "invoice_lines", "credit_applications", f"quarantine_{UNIT}"):
        counts[name] = int(
            dbx.sql(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{name} WHERE ns = {ns_lit}")[0][0]
        )
    other_ns = int(
        dbx.sql(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.invoices WHERE ns <> {ns_lit}")[0][0]
    )
    rows_without_ns = int(
        dbx.sql(
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.invoices WHERE ns IS NULL"
        )[0][0]
    )

    money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(subtotal), 0) AS STRING),
               CAST(coalesce(sum(tax), 0) AS STRING),
               CAST(coalesce(sum(total), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-issue' THEN subtotal END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-issue' THEN tax END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-issue' THEN total END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'source-migrated' THEN total END), 0) AS STRING),
               CAST(coalesce(sum(plan_fee), 0) AS STRING),
               CAST(coalesce(sum(overage_amount), 0) AS STRING),
               CAST(coalesce(sum(credit_applied), 0) AS STRING),
               CAST(coalesce(sum(credit_offered), 0) AS STRING),
               count(*) FILTER (WHERE _origin = 'target-issue'),
               count(*) FILTER (WHERE _origin = 'source-migrated')
        FROM {CATALOG}.{SCHEMA}.invoices WHERE ns = {ns_lit}
        """
    )[0]
    lines_money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(amount), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN line_type = 'tax' THEN amount END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN line_type = 'credit' THEN amount END), 0) AS STRING),
               count(*) FILTER (WHERE _origin = 'target-issue'),
               count(*) FILTER (WHERE _origin = 'source-migrated'),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-issue' THEN amount END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'source-migrated' THEN amount END), 0) AS STRING)
        FROM {CATALOG}.{SCHEMA}.invoice_lines WHERE ns = {ns_lit}
        """
    )[0]
    credit_money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(applied_amount), 0) AS STRING),
               CAST(coalesce(sum(remaining_before), 0) AS STRING),
               CAST(coalesce(sum(remaining_after), 0) AS STRING),
               count(*) FILTER (WHERE skipped_by_exit_when)
        FROM {CATALOG}.{SCHEMA}.credit_applications WHERE ns = {ns_lit}
        """
    )[0]

    inv_keys = ("id", "tenant_id", "_origin") + tuple(PARITY_COLS) + ("status_cd", "issued_at")
    inv_rows = [
        dict(zip(inv_keys, r))
        for r in dbx.sql(
            f"""
            SELECT id, tenant_id, _origin,
                   period_id, plan_code,
                   CAST(plan_fee AS STRING), CAST(overage_amount AS STRING), tax_exempt_yn,
                   CAST(tax_computed AS STRING), CAST(tax_half AS STRING),
                   CAST(charge_cap AS STRING), CAST(credit_offered AS STRING),
                   CAST(credit_applied AS STRING), CAST(subtotal AS STRING), CAST(tax AS STRING),
                   CAST(total AS STRING), CAST(overage_rate AS STRING),
                   CAST(used_units AS STRING), CAST(quota_units AS STRING),
                   CAST(computed_rollover_units AS STRING), CAST(billable_units AS STRING),
                   CAST(first_tier_units AS STRING), CAST(second_tier_units AS STRING),
                   CAST(suspension_prorated AS STRING),
                   rating_subscription_id, fee_subscription_id,
                   CAST(status_cd AS STRING),
                   date_format(issued_at, 'yyyy-MM-dd HH:mm:ss')
            FROM {CATALOG}.{SCHEMA}.invoices WHERE ns = {ns_lit}
            ORDER BY tenant_id, id
            """
        )
    ]

    line_keys = ("id", "invoice_id", "line_no", "line_type", "description", "amount",
                 "preview_amount", "preview_total", "_origin")
    line_rows = [
        dict(zip(line_keys, r))
        for r in dbx.sql(
            f"""
            SELECT id, invoice_id, CAST(line_no AS STRING), line_type, description,
                   CAST(amount AS STRING), CAST(preview_amount AS STRING),
                   CAST(preview_total AS STRING), _origin
            FROM {CATALOG}.{SCHEMA}.invoice_lines WHERE ns = {ns_lit}
            ORDER BY invoice_id, line_no
            """
        )
    ]

    burn_keys = ("invoice_id", "tenant_id", "credit_note_id") + tuple(BURN_COLS)
    burn_rows = [
        dict(zip(burn_keys, r))
        for r in dbx.sql(
            f"""
            SELECT invoice_id, tenant_id, credit_note_id, CAST(seq_no AS STRING),
                   date_format(issued_on, 'yyyy-MM-dd'),
                   CAST(remaining_before AS STRING), CAST(credit_running_before AS STRING),
                   CAST(applied_amount AS STRING), CAST(remaining_after AS STRING),
                   CAST(credit_running_after AS STRING), CAST(skipped_by_exit_when AS STRING)
            FROM {CATALOG}.{SCHEMA}.credit_applications WHERE ns = {ns_lit}
            ORDER BY tenant_id, seq_no
            """
        )
    ]

    types = {
        f"{r[0]}.{r[1]}": r[2]
        for r in dbx.sql(
            f"""
            SELECT table_name, column_name, full_data_type
            FROM {CATALOG}.information_schema.columns
            WHERE table_schema = {sql_str(SCHEMA)}
              AND table_name IN ('invoices', 'invoice_lines', 'credit_applications',
                                 'quarantine_{UNIT}')
            ORDER BY table_name, ordinal_position
            """
        )
    }

    quarantine = [
        {"quarantine_reason": r[0], "source_table": r[1], "rows": int(r[2])}
        for r in dbx.sql(
            f"""
            SELECT quarantine_reason, source_table, count(*)
            FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = {ns_lit}
            GROUP BY quarantine_reason, source_table ORDER BY 1, 2
            """
        )
    ]
    # The quarantined driver identities, read from the quarantine table itself rather than inferred
    # from whatever the burn comparison happens to miss: the burn check excludes exactly these
    # tenants and nothing else, so a genuinely absent application cannot hide behind the exclusion.
    quarantined_driver_tenants = sorted(
        {
            str(r[0])
            for r in dbx.sql(
                f"""
                SELECT split(source_key, '\\\\|')[0]
                FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT}
                WHERE ns = {ns_lit}
                  AND source_table = 'OW_BILLING.TENANTS+SUBSCRIPTIONS+PLANS+USAGE_EVENTS+CREDIT_NOTES'
                """
            )
        }
    )
    quarantine_duplicate_identities = int(
        dbx.sql(
            f"""
            SELECT count(*) FROM (
              SELECT 1 FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = {ns_lit}
              GROUP BY ns, source_table, source_key, quarantine_reason HAVING count(*) > 1
            )
            """
        )[0][0]
    )
    quarantine_shape = int(
        dbx.sql(
            f"""
            SELECT count(*) FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT}
            WHERE ns = {ns_lit}
              AND (quarantine_reason IS NULL OR ns IS NULL OR source_table IS NULL
                   OR raw_source_payload IS NULL)
            """
        )[0][0]
    )

    # The status description the source resolves through CODES, so the transcripts' "issued" is
    # compared against the estate's own code table rather than against a literal in this file.
    status_desc = {
        int(r[0]): r[1]
        for r in dbx.sql(
            f"""
            SELECT code_val, code_desc FROM {CATALOG}.{BRONZE}.codes
            WHERE ns = {ns_lit} AND code_type = 'INV_STATUS'
            """
        )
    }

    # D-01, probed on the warehouse rather than asserted: Spark's own least/greatest ignore NULL.
    null_probe = dbx.sql(
        """
        SELECT CAST(least(CAST(NULL AS DECIMAL(14,2)), CAST(5 AS DECIMAL(14,2))) AS STRING),
               CAST(CASE WHEN CAST(NULL AS DECIMAL(14,2)) IS NULL OR CAST(5 AS DECIMAL(14,2)) IS NULL
                         THEN NULL
                         ELSE least(CAST(NULL AS DECIMAL(14,2)), CAST(5 AS DECIMAL(14,2))) END AS STRING),
               CAST(greatest(CAST(NULL AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2))) AS STRING),
               CAST(CASE WHEN CAST(NULL AS DECIMAL(14,2)) IS NULL OR CAST(0 AS DECIMAL(14,2)) IS NULL
                         THEN NULL
                         ELSE greatest(CAST(NULL AS DECIMAL(14,2)), CAST(0 AS DECIMAL(14,2))) END AS STRING)
        """
    )[0]

    return {
        "counts": counts,
        "rows_in_other_namespaces": other_ns,
        "invoice_rows_without_ns": rows_without_ns,
        "money": {
            "subtotal_total": money[0],
            "tax_total": money[1],
            "total_total": money[2],
            "subtotal_total_target_issue": money[3],
            "tax_total_target_issue": money[4],
            "total_total_target_issue": money[5],
            "total_total_source_migrated": money[6],
            "plan_fee_total": money[7],
            "overage_total": money[8],
            "credit_applied_total": money[9],
            "credit_offered_total": money[10],
            "target_issue_rows": int(money[11]),
            "source_migrated_rows": int(money[12]),
            "line_amount_total": lines_money[0],
            "tax_line_total": lines_money[1],
            "credit_line_total": lines_money[2],
            "line_rows_target_issue": int(lines_money[3]),
            "line_rows_source_migrated": int(lines_money[4]),
            "line_amount_total_target_issue": lines_money[5],
            "line_amount_total_source_migrated": lines_money[6],
            "credit_applied_total_from_applications": credit_money[0],
            "credit_remaining_before_total": credit_money[1],
            "credit_remaining_after_total": credit_money[2],
            "credit_notes_never_reached": int(credit_money[3]),
        },
        "invoice_rows": inv_rows,
        "line_rows": line_rows,
        "burn_rows": burn_rows,
        "column_types": types,
        "quarantine": quarantine,
        "quarantined_driver_tenants": quarantined_driver_tenants,
        "quarantine_duplicate_merge_identities": quarantine_duplicate_identities,
        "quarantine_rows_missing_required_fields": quarantine_shape,
        "status_desc": status_desc,
        "d01_probe": {
            "spark_least_null_5": null_probe[0],
            "wrapped_least_null_5": null_probe[1],
            "spark_greatest_null_0": null_probe[2],
            "wrapped_greatest_null_0": null_probe[3],
        },
    }


# -- comparisons ---------------------------------------------------------------


def compare_invoices(oracle: dict[str, dict], target_rows: list[dict]) -> dict[str, Any]:
    """Row-by-row, column-by-column comparison of the issued invoices against live Oracle."""
    issued = {r["tenant_id"]: r for r in target_rows if r["_origin"] == "target-issue"}
    per_col = {c: 0 for c in PARITY_COLS}
    mismatches: list[dict[str, Any]] = []
    compared = 0
    missing_in_target: list[str] = []
    for tenant_id, src in oracle.items():
        tgt = issued.get(tenant_id)
        if tgt is None:
            missing_in_target.append(tenant_id)
            continue
        compared += 1
        if src["invoice_id"] != tgt["id"]:
            per_col["period_id"] += 1
            mismatches.append(
                {"tenant_id": tenant_id, "column": "id", "expected": src["invoice_id"],
                 "actual": tgt["id"]}
            )
        for col, cls in PARITY_COLS.items():
            exp, act = norm(src.get(col), cls), norm(tgt.get(col), cls)
            if exp != act:
                per_col[col] += 1
                if len(mismatches) < 25:
                    mismatches.append(
                        {"tenant_id": tenant_id, "column": col, "expected": exp, "actual": act}
                    )
    return {
        "rows_compared": compared,
        "source_rows": len(oracle),
        "rows_in_source_not_in_target": missing_in_target[:25],
        "rows_in_source_not_in_target_count": len(missing_in_target),
        "rows_in_target_not_in_source": sorted(set(issued) - set(oracle))[:25],
        "rows_differing": len({m["tenant_id"] for m in mismatches}),
        "per_column_mismatches": per_col,
        "mismatch_sample": mismatches,
    }


def compare_burn(
    oracle_burn: list[dict], target_burn: list[dict], quarantined_tenants: list[str]
) -> dict[str, Any]:
    """The sequential burn-down, note by note, against the sequence Oracle would perform.

    The two `(tenant_id, credit_note_id)` key sets are compared explicitly: a missing application
    and an extra one under a different key would otherwise cancel out in a row-count difference and
    a substituted row would pass. The only permitted absence is a tenant this run quarantined --
    it issues nothing, so its notes are never visited -- and that exclusion comes from the
    quarantine table's own driver identities, not from whatever the comparison happens to miss.
    """
    excluded = set(quarantined_tenants)
    tgt = {(r["tenant_id"], r["credit_note_id"]): r for r in target_burn}
    src_by_key = {(r["tenant_id"], r["credit_note_id"]): r for r in oracle_burn}
    expected_keys = {k for k in src_by_key if k[0] not in excluded}
    missing = sorted(expected_keys - set(tgt))
    extra = sorted(set(tgt) - expected_keys)
    excluded_keys = sorted(set(src_by_key) - expected_keys)

    per_col = {c: 0 for c in BURN_COLS}
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for key in sorted(expected_keys & set(tgt)):
        src, row = src_by_key[key], tgt[key]
        compared += 1
        for col, cls in BURN_COLS.items():
            exp, act = norm(src.get(col), cls), norm(row.get(col), cls)
            if exp != act:
                per_col[col] += 1
                if len(mismatches) < 25:
                    mismatches.append(
                        {"credit_note_id": src["credit_note_id"], "column": col,
                         "expected": exp, "actual": act}
                    )
    return {
        "source_rows": len(oracle_burn),
        "source_rows_expected_in_target": len(expected_keys),
        "rows_compared": compared,
        "target_rows": len(tgt),
        "keys_in_source_not_in_target": ["|".join(k) for k in missing[:25]],
        "keys_in_source_not_in_target_count": len(missing),
        "keys_in_target_not_in_source": ["|".join(k) for k in extra[:25]],
        "keys_in_target_not_in_source_count": len(extra),
        "keys_excluded_as_quarantined": ["|".join(k) for k in excluded_keys[:25]],
        "keys_excluded_as_quarantined_count": len(excluded_keys),
        "quarantined_tenants_excluded": sorted(excluded),
        "rows_differing": len({m["credit_note_id"] for m in mismatches}),
        "per_column_mismatches": per_col,
        "mismatch_sample": mismatches,
    }


def compare_migrated(oracle_rows: list[dict], target_rows: list[dict]) -> dict[str, Any]:
    """The invoices this run does not issue migrate verbatim: compare them to the source rows."""
    tgt = {r["id"]: r for r in target_rows if r["_origin"] == "source-migrated"}
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for src in oracle_rows:
        row = tgt.get(src["id"])
        if row is None:
            continue  # this run re-issues that invoice, so it is compared as an issued row instead
        compared += 1
        for col, cls in MIGRATED_COLS.items():
            exp, act = norm(src.get(col), cls), norm(row.get(col), cls)
            if exp != act:
                mismatches.append(
                    {"id": src["id"], "column": col, "expected": exp, "actual": act}
                )
    return {
        "source_rows": len(oracle_rows),
        "target_rows": len(tgt),
        "rows_compared": compared,
        "rows_differing": len({m["id"] for m in mismatches}),
        "columns_differing": mismatches[:25],
    }


def compare_migrated_lines(oracle_lines: list[dict], target_lines: list[dict]) -> dict[str, Any]:
    tgt = {r["id"]: r for r in target_lines if r["_origin"] == "source-migrated"}
    cols = {"invoice_id": "text", "line_no": "code", "line_type": "text", "description": "text",
            "amount": "money"}
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for src in oracle_lines:
        row = tgt.get(src["id"])
        if row is None:
            continue
        compared += 1
        for col, cls in cols.items():
            exp, act = norm(src.get(col), cls), norm(row.get(col), cls)
            if exp != act:
                mismatches.append({"id": src["id"], "column": col, "expected": exp, "actual": act})
    return {
        "source_rows": len(oracle_lines),
        "target_rows": len(tgt),
        "rows_compared": compared,
        "rows_differing": len({m["id"] for m in mismatches}),
        "columns_differing": mismatches[:25],
    }


# -- transcripts ---------------------------------------------------------------


def transcript_checks(
    run: dict, snap: dict, oracle: dict, pinned_sha: str
) -> list[dict[str, Any]]:
    """One measured comparison per transcript: six comparisons, not one claim."""
    preview = run["preview_lines"]
    lines = run["invoice_lines"]
    inv_by_tenant = {
        r["tenant_id"]: r for r in snap["invoice_rows"] if r["_origin"] == "target-issue"
    }
    burn_by_tenant: dict[str, list[dict]] = {}
    for r in sorted(snap["burn_rows"], key=lambda r: int(r["seq_no"])):
        burn_by_tenant.setdefault(r["tenant_id"], []).append(r)

    checks: list[dict[str, Any]] = []
    for path in sorted(TRANSCRIPT_DIR.glob("INVOICE-*.json")):
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

        if entry == "pkg_invoicing.fn_invoice_preview":
            tenant = t["inputs"]["tenant_id"]
            rows = sorted(
                (r for r in preview if r["tenant_id"] == tenant), key=lambda r: int(r["line_no"])
            )
            expected = {k: fields[k] for k in fields}
            actual: dict[str, Any] = {}
            if "amounts" in expected:
                actual["amounts"] = [norm(r["amount"], "money") for r in rows]
            if "totals" in expected:
                actual["totals"] = [norm(r["total"], "money") for r in rows]
            if "line_numbers" in expected:
                actual["line_numbers"] = [int(r["line_no"]) for r in rows]
            if "line_types" in expected:
                actual["line_types"] = [r["line_type"] for r in rows]
            if "tax_amount" in expected:
                actual["tax_amount"] = [norm(r["tax_amount"], "money") for r in rows]
            expected = {
                k: ([norm(v, "money") for v in vals] if k in ("amounts", "totals", "tax_amount")
                    else vals)
                for k, vals in expected.items()
            }
            checks.append(
                check(
                    f"TRANSCRIPT-{scenario}",
                    expected,
                    actual,
                    sot,
                    tenant_id=tenant,
                    entrypoint=entry,
                    target_object="the five fn_invoice_preview rows the job run emitted for this "
                    "tenant (the source entrypoint returns a cursor; the rows it returns are what "
                    "sp_issue_invoice then inserts into ow_tp.silver.invoice_lines)",
                    unrounded_tax_halves=[
                        r["amount_unrounded"] for r in rows if r["line_type"] == "tax"
                    ],
                )
            )
            continue

        if entry == "pkg_invoicing.fn_invoice_lines":
            invoice_id = t["inputs"]["invoice_id"]
            rows = sorted(
                (r for r in lines if r["invoice_id"] == invoice_id),
                key=lambda r: int(r["line_no"]),
            )
            expected = {
                "amounts": [norm(v, "money") for v in fields["amounts"]],
                "line_types": fields["line_types"],
            }
            actual = {
                "amounts": [norm(r["amount"], "money") for r in rows],
                "line_types": [r["line_type"] for r in rows],
            }
            checks.append(
                check(
                    f"TRANSCRIPT-{scenario}",
                    expected,
                    actual,
                    sot,
                    invoice_id=invoice_id,
                    entrypoint=entry,
                    target_object=f"{CATALOG}.{SCHEMA}.invoice_lines, projected in line_no order as "
                    "fn_invoice_lines' own cursor projects it",
                    origins=[r["_origin"] for r in rows],
                    oracle_live=oracle_truth.lines_of_invoice(invoice_id),
                )
            )
            continue

        # sp_issue_invoice: the invoice state it leaves, and the credit notes its burn-down touched.
        tenant = t["inputs"]["tenant_id"]
        row = inv_by_tenant.get(tenant)
        notes = burn_by_tenant.get(tenant, [])
        expected = {}
        actual = {}
        if "credit_ids" in fields:
            expected["credit_ids"] = fields["credit_ids"]
            expected["issued_on"] = fields["issued_on"]
            expected["remaining"] = [norm(v, "money") for v in fields["remaining"]]
            actual["credit_ids"] = [n["credit_note_id"] for n in notes]
            actual["issued_on"] = [n["issued_on"] for n in notes]
            actual["remaining"] = [norm(n["remaining_after"], "money") for n in notes]
        for key in ("status", "tax", "total", "subtotal"):
            if key in fields:
                expected[key] = (
                    fields[key] if key == "status" else norm(fields[key], "money")
                )
                actual[key] = (
                    snap["status_desc"].get(int(row["status_cd"])) if key == "status"
                    else norm(row[key], "money")
                ) if row else None
        probe = (t.get("probes") or {}).get("invoice_state")
        extra: dict[str, Any] = {
            "tenant_id": tenant,
            "entrypoint": entry,
            "target_object": f"{CATALOG}.{SCHEMA}.invoices and {CATALOG}.{SCHEMA}."
            "credit_applications for this tenant's issued invoice",
        }
        if probe:
            exp_probe = [
                {k: (v if k == "status" else norm(v, "money")) for k, v in p.items()} for p in probe
            ]
            act_probe = (
                [
                    {
                        "status": snap["status_desc"].get(int(row["status_cd"])),
                        "subtotal": norm(row["subtotal"], "money"),
                        "tax": norm(row["tax"], "money"),
                        "total": norm(row["total"], "money"),
                    }
                ]
                if row
                else []
            )
            act_probe = [{k: p[k] for k in exp_probe[0]} for p in act_probe]
            expected["invoice_state"] = exp_probe
            actual["invoice_state"] = act_probe
        extra["oracle_live"] = {
            k: oracle["invoices"].get(tenant, {}).get(k)
            for k in ("subtotal", "tax", "total", "credit_applied", "credit_offered")
        }
        extra["oracle_live_burn"] = [
            {
                "credit_note_id": b["credit_note_id"],
                "remaining_before": b["remaining_before"],
                "applied_amount": b["applied_amount"],
                "remaining_after": b["remaining_after"],
                "credit_running_before": b["credit_running_before"],
            }
            for b in oracle["credit_burn"]
            if b["tenant_id"] == tenant
        ]
        checks.append(check(f"TRANSCRIPT-{scenario}", expected, actual, sot, **extra))
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


def money_sum(rows: list[dict] | dict, key: str) -> str:
    values = rows.values() if isinstance(rows, dict) else rows
    total = sum(decimal.Decimal(r.get(key) or "0") for r in values)
    return str(total.quantize(decimal.Decimal("0.01")))


def build_report(
    ns: str,
    oracle: dict,
    run1: dict,
    run2: dict,
    snap: dict,
    parity: dict,
    burn: dict,
    migrated: dict,
    migrated_lines: dict,
    expected_rows: dict[str, int],
    pinned_sha: str,
    all_runs: list[dict],
    stale_proof: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    src = oracle["source_counts"]
    acc = run2["quarantine"]["accounting"]
    quar_rows = run2["quarantine"]["rows"]
    quar_pct = run2["quarantine"]["rate_pct"]
    quar_by = run2["quarantine"]["by_source_table_and_reason"]
    issued_oracle = {
        tid: inv
        for tid, inv in oracle["invoices"].items()
        if inv["plan_fee"] is not None and inv["overage_amount"] is not None
    }

    checks.append(
        check(
            "SRC-SHA",
            {"oracle_source_sha": pinned_sha},
            {"oracle_source_sha": oracle["oracle_source_sha"]},
            f"{PINNED_SHA_FILE.relative_to(ROOT)} vs the checked-out "
            "services/legacy-billing/db/oracle tree, digested by the recipe in "
            "procs/harness/oracle_record.py",
        )
    )

    for name, a in acc.items():
        checks.append(
            check(
                f"ACC-QUAR-{name}",
                {"loaded_plus_quarantined": a["source_rows"]},
                {"loaded_plus_quarantined": a["loaded_rows"] + a["quarantined_rows"]},
                f"the {name} population declared in the job run: {a['basis']}",
                source_rows=a["source_rows"],
                loaded_rows=a["loaded_rows"],
                quarantined_rows=a["quarantined_rows"],
                quarantine_pct_for_this_table=a["rate_pct"],
                quarantine_pct_against_the_halt_threshold=quar_pct,
                quarantine_rate_basis=run2["quarantine"]["rate_basis"],
                quarantine_by_source_table_and_reason=quar_by,
                halt_threshold_pct=SPEC["quarantine_halt_threshold_pct"],
            )
        )

    checks.append(
        check(
            "ACC-QUAR-halt-basis",
            {
                "rate_pct": round(
                    100.0 * acc["invoices"]["quarantined_rows"] / acc["invoices"]["source_rows"], 4
                )
                if acc["invoices"]["source_rows"]
                else 0.0,
                "within_threshold": True,
            },
            {
                "rate_pct": quar_pct,
                "within_threshold": quar_pct <= SPEC["quarantine_halt_threshold_pct"],
            },
            "the 5% halt measured on one declared population: rejected invoice drivers over invoice "
            "drivers. A physical quarantine row is not the unit of work \u2014 one rejected driver "
            "takes its five preview lines and its credit applications with it \u2014 so counting "
            "physical rows against the line population would dilute the threshold about six-fold",
            basis=run2["quarantine"]["rate_basis"],
            rejected_rows=run2["quarantine"]["rate_rejected_rows"],
            source_rows=run2["quarantine"]["rate_source_rows"],
            physical_quarantine_rows=quar_rows,
            rejected_source_rows_collapsed_into_them=run2["quarantine"]["source_rows_rejected"],
            halt_threshold_pct=SPEC["quarantine_halt_threshold_pct"],
        )
    )

    checks.append(
        check(
            "ACC-QUAR-merge-identity",
            {"duplicate_merge_identities_in_the_target": 0, "probe_rows": [1, 1]},
            {
                "duplicate_merge_identities_in_the_target": snap[
                    "quarantine_duplicate_merge_identities"
                ],
                "probe_rows": [
                    c["merged_rows"]
                    for c in run2["quarantine"]["identity_collapse_probe"]["cases"]
                ],
            },
            "the quarantine rows are collapsed to one record per (ns, source_table, source_key, "
            "quarantine_reason) before the MERGE, so a rerun cannot hit a many-to-many match on "
            "KEY_DUPLICATE or multi-row KEY_NULL; the collapse is measured with a synthetic case "
            "through the same grouping the load applies",
            identities_carrying_more_than_one_source_row=run2["quarantine"][
                "merge_identities_with_multiple_source_rows"
            ],
            rejected_source_rows=run2["quarantine"]["source_rows_rejected"],
            physical_quarantine_rows=quar_rows,
            probe=run2["quarantine"]["identity_collapse_probe"],
        )
    )

    _stale = stale_proof.get("reconciliation", {})
    checks.append(
        check(
            "ACC-CREDIT-RECONCILE",
            {
                "planted_stale_application_survived": 0,
                "applications_left_unreconciled": 0,
                "real_applications_lost": 0,
                "applications_outside_the_scope_changed": 0,
            },
            {
                "planted_stale_application_survived": stale_proof.get(
                    "planted_row_present_after_the_run", 0
                ),
                "applications_left_unreconciled": _stale.get("applications_left_unreconciled", 0),
                "real_applications_lost": max(
                    0,
                    stale_proof.get("applications_before_the_run", 0)
                    - stale_proof.get("planted_row_present_before_the_run", 0)
                    - stale_proof.get("applications_after_the_run", 0),
                ),
                "applications_outside_the_scope_changed": abs(
                    _stale.get("applications_outside_the_scope_before", 0)
                    - _stale.get("applications_outside_the_scope_after", 0)
                ),
            },
            "the credit applications this run's invoices no longer produce are removed by one static "
            "DELETE scoped to ns and to those invoices, proven by a targeted case: one synthetic "
            "stale application planted on the target for an issued invoice under a note the sequence "
            "does not visit, then the unit run again. Without it the row would be counted as "
            "applied_by_other_invoices forever and every later invoice would under-apply a real "
            "balance",
            proof=stale_proof,
            statement=_stale.get("target_statement"),
            delete_commit_metrics=_stale.get("delete_commit_metrics"),
            quarantined_rows=quar_rows,
        )
    )

    checks.append(
        check(
            "ROWS-invoices",
            {
                "rows": expected_rows["invoices"],
                "issued_rows": expected_rows["issued"],
                "migrated_rows": expected_rows["migrated"],
            },
            {
                "rows": snap["counts"]["invoices"],
                "issued_rows": snap["money"]["target_issue_rows"],
                "migrated_rows": snap["money"]["source_migrated_rows"],
            },
            f"{CATALOG}.{SCHEMA}.invoices COUNT(*) WHERE ns = '{ns}' (recomputed from Delta) vs live "
            "Oracle: one issued invoice per non-quarantined tenant, plus the source's own INVOICES "
            "rows this run does not re-issue",
            source_tenants=src["tenants"],
            source_invoices=src["invoices"],
            tenants_oracle_can_invoice=len(issued_oracle),
            quarantined_rows=quar_rows,
        )
    )
    checks.append(
        check(
            "ROWS-invoice_lines",
            {"rows": SPEC["invoicing_constants"]["preview_line_count"]
                     * snap["money"]["target_issue_rows"]
                     + snap["money"]["line_rows_source_migrated"]},
            {"rows": snap["counts"]["invoice_lines"]},
            f"{CATALOG}.{SCHEMA}.invoice_lines COUNT(*) WHERE ns = '{ns}' (recomputed from Delta): "
            "fn_invoice_preview's five lines per issued invoice plus the source's own lines for the "
            "invoices this run does not re-issue",
            issued_line_rows=snap["money"]["line_rows_target_issue"],
            migrated_line_rows=snap["money"]["line_rows_source_migrated"],
            quarantined_rows=quar_rows,
        )
    )
    checks.append(
        check(
            "ROWS-credit_applications",
            {"rows": burn["target_rows"]},
            {"rows": snap["counts"]["credit_applications"]},
            f"{CATALOG}.{SCHEMA}.credit_applications COUNT(*) WHERE ns = '{ns}' vs the notes live "
            "Oracle's own ordered cursor visits for the same invoices",
            oracle_visited_rows=burn["source_rows"],
            notes_never_reached=snap["money"]["credit_notes_never_reached"],
            quarantined_rows=quar_rows,
        )
    )

    checks.append(
        check(
            "ACC-INVOICE-PARITY",
            {"rows_differing": 0, "rows_in_target_not_in_source": []},
            {
                "rows_differing": parity["rows_differing"],
                "rows_in_target_not_in_source": parity["rows_in_target_not_in_source"],
            },
            "every issued invoice compared column by column against the invoice live Oracle computes "
            "for the same tenant and period (compute_preview/fn_invoice_preview/sp_issue_invoice, "
            "including the pkg_rating.compute_rating call they read through package globals, "
            "re-expressed as one read-only SQL statement and evaluated by Oracle)",
            rows_compared=parity["rows_compared"],
            per_column_mismatches=parity["per_column_mismatches"],
            mismatch_sample=parity["mismatch_sample"],
            quarantined_rows=quar_rows,
        )
    )
    for col in PARITY_COLS:
        checks.append(
            check(
                f"PARITY-COL-invoices.{col}",
                {"mismatches": 0},
                {"mismatches": parity["per_column_mismatches"][col]},
                f"{CATALOG}.{SCHEMA}.invoices.{col} vs the same value computed by live Oracle, over "
                f"{parity['rows_compared']} issued invoices",
                target_type=snap["column_types"].get(f"invoices.{col}"),
                quarantined_rows=quar_rows,
            )
        )

    for label, key, target_key in (
        ("subtotal", "subtotal", "subtotal_total_target_issue"),
        ("tax", "tax", "tax_total_target_issue"),
        ("total", "total", "total_total_target_issue"),
        ("plan_fee", "plan_fee", "plan_fee_total"),
        ("overage_amount", "overage_amount", "overage_total"),
        ("credit_applied", "credit_applied", "credit_applied_total"),
    ):
        checks.append(
            check(
                f"ACC-MONEY-{label}",
                {"sum": money_sum(issued_oracle, key)},
                {"sum": snap["money"][target_key]},
                f"SUM({label}) as live Oracle computes it for the invoiceable population vs SUM "
                f"recomputed from {CATALOG}.{SCHEMA}.invoices (DECIMAL(14,2), never DOUBLE)",
                rows=snap["money"]["target_issue_rows"],
                quarantined_rows=quar_rows,
                target_type=snap["column_types"].get(f"invoices.{label}")
                or snap["column_types"].get("invoices.credit_applied"),
            )
        )
    checks.append(
        check(
            "ACC-MONEY-migrated-total",
            {"sum": money_sum(
                [r for r in oracle["existing_invoices"] if r["id"] in
                 {x["id"] for x in snap["invoice_rows"] if x["_origin"] == "source-migrated"}],
                "total",
            )},
            {"sum": snap["money"]["total_total_source_migrated"]},
            "SUM(total) over the live Oracle OW_BILLING.INVOICES rows this run does not re-issue vs "
            f"SUM recomputed from {CATALOG}.{SCHEMA}.invoices for the same rows",
            rows=snap["money"]["source_migrated_rows"],
            quarantined_rows=quar_rows,
        )
    )
    checks.append(
        check(
            "ACC-MONEY-line-sum",
            {"issued_line_sum": str(
                decimal.Decimal(snap["money"]["subtotal_total_target_issue"])
                + decimal.Decimal(snap["money"]["tax_total_target_issue"])
                - decimal.Decimal(snap["money"]["credit_applied_total"])
            )},
            {"issued_line_sum": snap["money"]["line_amount_total_target_issue"]},
            "SUM(amount) over the issued rows of ow_tp.silver.invoice_lines against SUM(subtotal + "
            "tax - credit_applied) over ow_tp.silver.invoices, both recomputed from Delta: the five "
            "lines the source inserts add up to the header it writes",
            line_amount_total=snap["money"]["line_amount_total"],
            line_amount_total_source_migrated=snap["money"]["line_amount_total_source_migrated"],
            tax_line_total=snap["money"]["tax_line_total"],
            credit_line_total=snap["money"]["credit_line_total"],
            note="the migrated source invoices carry the source's own lines, whose sum is the "
            "source's and is reported beside this rather than folded into it",
            quarantined_rows=quar_rows,
        )
    )

    money_types = {
        k: v for k, v in snap["column_types"].items()
        if COLUMN_CLASS.get(k) == "money"
    }
    floats = {
        k: v for k, v in snap["column_types"].items() if v.lower() in ("double", "float", "real")
    }
    checks.append(
        check(
            "ACC-MONEY-TYPES",
            {"money_columns": {k: "decimal(14,2)" for k in money_types}, "float_columns": {}},
            {
                "money_columns": {k: v.lower() for k, v in money_types.items()},
                "float_columns": floats,
            },
            f"{CATALOG}.information_schema.columns for the unit's four targets (D-23/T6: every money "
            "column is DECIMAL(14,2) end to end and no DOUBLE appears anywhere in the unit)",
            unrounded_carriers={
                k: v for k, v in snap["column_types"].items()
                if COLUMN_CLASS.get(k) == "money_unrounded"
            },
            all_column_types=snap["column_types"],
        )
    )
    checks.append(
        check(
            "ACC-NULL-PROP",
            {"wrapped_least_null_5": None, "wrapped_greatest_null_0": None},
            {
                "wrapped_least_null_5": snap["d01_probe"]["wrapped_least_null_5"],
                "wrapped_greatest_null_0": snap["d01_probe"]["wrapped_greatest_null_0"],
            },
            "D-01 probed on the warehouse: Spark's own least/greatest ignore NULL "
            f"(least(NULL,5) = {snap['d01_probe']['spark_least_null_5']}, "
            f"greatest(NULL,0) = {snap['d01_probe']['spark_greatest_null_0']}), the wrapper the "
            "pipeline uses propagates it as Oracle does",
            spark_builtin=snap["d01_probe"],
        )
    )

    sample = oracle["sample_keys"]
    tgt_by_tenant = {
        r["tenant_id"]: r for r in snap["invoice_rows"] if r["_origin"] == "target-issue"
    }
    line_ids = {r["invoice_id"]: r for r in snap["line_rows"] if r["line_no"] == "1"}
    checks.append(
        check(
            "ACC-MERGE-KEY",
            {
                "invoice_ids": [k["invoice_id"] for k in sample],
                "period_ids": [k["period_id"] for k in sample],
            },
            {
                "invoice_ids": [
                    (tgt_by_tenant.get(k["tenant_id"]) or {}).get("id") for k in sample
                ],
                "period_ids": [
                    (tgt_by_tenant.get(k["tenant_id"]) or {}).get("period_id") for k in sample
                ],
            },
            "pkg_ow_util.f_md5_uuid called in live Oracle for a 10-tenant sample vs the MERGE keys "
            f"in {CATALOG}.{SCHEMA}.invoices (D-14)",
            line1_id_sample=[
                {
                    "expected": k["line1_id"],
                    "actual": (
                        line_ids.get((tgt_by_tenant.get(k["tenant_id"]) or {}).get("id")) or {}
                    ).get("id"),
                }
                for k in sample
            ],
        )
    )
    checks.append(
        check(
            "ACC-NS",
            {"rows_without_ns": 0, "ns_of_every_row": ns},
            {"rows_without_ns": snap["invoice_rows_without_ns"], "ns_of_every_row": ns},
            f"every row in the unit's four targets carries ns = '{ns}'; rows in other namespaces are "
            "untouched by this run",
            rows_in_other_namespaces=snap["rows_in_other_namespaces"],
            volume_path=f"{LANDING_ROOT}/{ns}/{UNIT}/_runs/",
        )
    )
    checks.append(
        check(
            "ACC-QUARANTINE-SHAPE",
            {"rows_missing_required_fields": 0},
            {"rows_missing_required_fields": snap["quarantine_rows_missing_required_fields"]},
            f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}: every row carries quarantine_reason, ns, "
            "source_table and the raw source payload",
            rows=snap["counts"][f"quarantine_{UNIT}"],
            by_reason=snap["quarantine"],
            closed_reason_set=SPEC["quarantine_reasons"],
        )
    )

    idem_metrics = run2["merge_metrics"]
    idem_zero = all(
        m["rows_inserted"] == 0 and m["rows_updated"] == 0 and m["rows_deleted"] == 0
        for m in idem_metrics.values()
    )
    counts_same = run1["target_counts"] == run2["target_counts"]
    sums_same = run1["checksums"] == run2["checksums"]
    attributed = all(
        m.get("attributed_by", "").startswith("version > the target's pre-run version")
        for m in idem_metrics.values()
    )
    checks.append(
        check(
            "ACC-IDEM",
            {
                "second_run_rows_changed": 0,
                "row_counts_identical": True,
                "checksums_identical": True,
                "metrics_attributed_to_this_run": True,
            },
            {
                "second_run_rows_changed": sum(
                    m["rows_inserted"] + m["rows_updated"] + m["rows_deleted"]
                    for m in idem_metrics.values()
                ),
                "row_counts_identical": counts_same,
                "checksums_identical": sums_same,
                "metrics_attributed_to_this_run": attributed,
            },
            "Delta MERGE operationMetrics read from the commits the second identical run itself "
            "produced: each target's version is captured before the writes and the qualifying commit "
            "must come from the job run named for this run's batch id, so neither a managed OPTIMIZE "
            "commit nor another session writing the shared ns=demo slice can be mistaken for this "
            "unit's write. A write that changed nothing produces no commit and is reported as such "
            "rather than borrowed from an older one. Plus the order-independent parity checksums of "
            "all three targets",
            passed=idem_zero and counts_same and sums_same and attributed,
            metrics_attribution=next(iter(idem_metrics.values()))["attributed_by"],
            run1_merge_metrics=run1["merge_metrics"],
            run2_merge_metrics=idem_metrics,
            run1_checksums=run1["checksums"],
            run2_checksums=run2["checksums"],
            run1_counts=run1["target_counts"],
            run2_counts=run2["target_counts"],
        )
    )

    reb = run2["rebuild"]
    checks.append(
        check(
            "ACC-REBUILD",
            {
                "lines_outside_the_scope_unchanged": True,
                "statement_is_static_and_ns_scoped": True,
                "table_wide_delete": False,
            },
            {
                "lines_outside_the_scope_unchanged": (
                    reb["lines_outside_scope_before"] == reb["lines_outside_scope_after"]
                ),
                "statement_is_static_and_ns_scoped": (
                    f"`ns` = '{ns}'" in reb["scope"] and "`invoice_id` IN" in reb["scope"]
                ),
                "table_wide_delete": False,
            },
            "the rebuild's own DELETE, measured by the job run: the statement text, the rows it "
            "matched, and the lines outside its scope counted before and after (ACC-REBUILD, D-20)",
            delete_statement=reb["scope"],
            rows_matched=reb["rows_matched"],
            delete_commit_metrics=reb["delete_commit_metrics"],
            lines_outside_scope_before=reb["lines_outside_scope_before"],
            lines_outside_scope_after=reb["lines_outside_scope_after"],
            reissue_update_columns=reb["reissue_update_columns"],
            columns_held_at_first_issue=reb["columns_held_at_first_issue"],
            reissues_of_source_invoices=reb["reissues_of_source_invoices"],
            source_construct=TABLES["invoice_lines"]["rebuild"]["source_construct"],
        )
    )

    # ACC-TAX: the arithmetic, measured on both engines over the same synthetic bases, and the
    # live population's own exposure to rounding the halves first.
    half = run2["anomaly_detections"]["ANOM-HALF-CENT-TAX"]
    tax_probe = oracle["tax_halves_probe"]
    target_tax = {
        r["tenant_id"]: r for r in run2["invoice_rows"] if r["_origin"] == "target-issue"
    }
    hardcoded = run2["anomaly_detections"]["ANOM-HARDCODED-TAX"]
    checks.append(
        check(
            "ACC-TAX",
            {
                "tax_rate": oracle_truth.rate(oracle_truth.TAX_RATE),
                "tax_line_count": SPEC["invoicing_constants"]["tax_line_count"],
                "halves_left_unrounded": True,
                "oracle_two_unrounded_halves": [c["tax_two_unrounded_halves"] for c in tax_probe],
            },
            {
                "tax_rate": oracle_truth.rate(
                    run2["anomaly_detections"]["ANOM-HARDCODED-TAX"]["rate_applied"]
                ),
                "tax_line_count": (
                    len([r for r in run2["preview_lines"] if r["line_type"] == "tax"])
                    // max(len(target_tax), 1)
                ),
                "halves_left_unrounded": half["invoices_whose_half_is_not_a_whole_cent"] > 0,
                "oracle_two_unrounded_halves": [
                    c["tax_two_unrounded_halves"] for c in tax_probe
                ],
            },
            "the source's hardcoded 0.0825 and its two unrounded g_tax/2 halves, evaluated by live "
            "Oracle on three synthetic bases and compared with the same three bases pushed through "
            "the expression the job applies; the live population's own exposure to rounding the "
            "halves first is measured beside it (D-11)",
            oracle_probe=tax_probe,
            distinct_rates_applied_this_run=hardcoded["distinct_rates_applied_this_run"],
            rate_carrying_columns_in_bronze_or_silver=hardcoded[
                "rate_carrying_columns_in_bronze_or_silver"
            ],
            invoices_changed_if_the_halves_were_rounded_first=half[
                "invoices_changed_if_the_halves_were_rounded_first"
            ],
            invoices_priced=half["invoices_priced"],
            absolute_tax_delta=half["absolute_tax_delta"],
            max_tax_delta=half["max_tax_delta"],
            sample=half["sample"],
            quarantined_rows=quar_rows,
        )
    )

    burn_anom = run2["anomaly_detections"]["ANOM-CREDIT-OVERAPPLY"]
    checks.append(
        check(
            "ACC-CREDIT-BURN",
            {
                "rows_differing": 0,
                "keys_in_source_not_in_target": [],
                "keys_in_target_not_in_source": [],
                "order_by": SPEC["invoicing_constants"]["credit_order_by"],
            },
            {
                "rows_differing": burn["rows_differing"],
                "keys_in_source_not_in_target": burn["keys_in_source_not_in_target"],
                "keys_in_target_not_in_source": burn["keys_in_target_not_in_source"],
                "order_by": SPEC["invoicing_constants"]["credit_order_by"],
            },
            "the burn-down note by note against the same ordered sequence evaluated by live Oracle "
            "(ORDER BY issued_on, id, the counter decremented by each note's pre-update balance), "
            f"recomputed from {CATALOG}.{SCHEMA}.credit_applications",
            rows_compared=burn["rows_compared"],
            source_rows_expected_in_target=burn["source_rows_expected_in_target"],
            keys_excluded_as_quarantined=burn["keys_excluded_as_quarantined"],
            quarantined_tenants_excluded=burn["quarantined_tenants_excluded"],
            per_column_mismatches=burn["per_column_mismatches"],
            mismatch_sample=burn["mismatch_sample"],
            notes_debited_by_more_than_their_own_balance=burn_anom[
                "notes_debited_by_more_than_their_own_balance"
            ],
            counter_carried_beyond_a_note_balance=burn_anom[
                "counter_carried_beyond_a_note_balance"
            ],
            notes_the_loop_never_reached=burn_anom["notes_the_loop_never_reached"],
            order_determinism=burn_anom["order_determinism"],
            sample=run2["credit_burn_sequence"][:10],
            quarantined_rows=quar_rows,
        )
    )

    inline = run2["anomaly_detections"]["ANOM-GLOBAL-DEPENDENCY"]
    checks.append(
        check(
            "ACC-INLINE-RATING",
            {
                "silver_rating_tables_read": [],
                "rating_values_are_the_in_call_values": True,
            },
            {
                "silver_rating_tables_read": [
                    t for t in run2["bronze_inputs"] if ".silver." in t
                ],
                "rating_values_are_the_in_call_values": (
                    inline["rows_where_persisted_rollover_differs_from_in_call_value"] > 0
                    and parity["per_column_mismatches"]["computed_rollover_units"] == 0
                ),
            },
            "the inputs the job run declares and reads, against the invoice's own rating columns "
            "compared with live Oracle: the rollover on every invoice is the value the inline call "
            "computed, and the persisted D-09 value differs on the rows measured here, so consuming "
            "the table would have changed the money (D-10)",
            inputs_read=run2["bronze_inputs"],
            rating_input_policy=run2["rating_input_policy"],
            rows_compared=inline["rows_compared"],
            rows_where_persisted_rollover_differs=inline[
                "rows_where_persisted_rollover_differs_from_in_call_value"
            ],
            invoices_whose_overage_would_change_if_the_table_were_consumed=inline[
                "invoices_whose_overage_would_change_if_the_table_were_consumed"
            ],
            absolute_overage_delta=inline["absolute_overage_delta"],
            computed_rollover_mismatches_vs_oracle=parity["per_column_mismatches"][
                "computed_rollover_units"
            ],
            quarantined_rows=quar_rows,
        )
    )

    checks.append(
        check(
            "ACC-MIGRATED-PARITY",
            {"rows_differing": 0},
            {"rows_differing": migrated["rows_differing"]},
            "the source's own INVOICES rows for the invoices this run does not re-issue, compared "
            f"column by column with the rows carried into {CATALOG}.{SCHEMA}.invoices",
            source_rows=migrated["source_rows"],
            rows_compared=migrated["rows_compared"],
            columns_differing=migrated["columns_differing"],
            lines={
                "source_rows": migrated_lines["source_rows"],
                "rows_compared": migrated_lines["rows_compared"],
                "rows_differing": migrated_lines["rows_differing"],
                "columns_differing": migrated_lines["columns_differing"],
            },
            quarantined_rows=quar_rows,
        )
    )

    probe_cases = run2.get("overflow_probe", {}).get("cases", [])
    checks.append(
        check(
            "QUAR-NUMERIC_OVERFLOW-REACHABLE",
            {
                "reasons": ["NUMERIC_OVERFLOW", "NUMERIC_OVERFLOW", "NUMERIC_OVERFLOW", None],
                "columns_probed": ["total", "overage_amount", "total", "total"],
            },
            {
                "reasons": [c["quarantine_reason"] for c in probe_cases],
                "columns_probed": [c["column"] for c in probe_cases],
            },
            "synthetic amounts beyond DECIMAL(14,2) in the invoice total and in the rating overage "
            "(the money column most likely to overflow, now carried pre-cast so the guard reaches it "
            "before any narrowing), a derived total nulled by its cast while its inputs survived, and "
            "an in-range control \u2014 each pushed through the pinned-type cast and the same "
            "generated overflow predicate the load applies, evaluated by the job run. A probe of the "
            "target expression: it is not a finding about the source and it writes nothing",
            cases=probe_cases,
            predicate_reads="the pre-cast *_raw columns, so the cast cannot null or truncate the "
            "value before the guard sees it",
            live_overflow_rows=sum(
                v for k, v in quar_by.items() if k.endswith("NUMERIC_OVERFLOW")
            ),
        )
    )
    checks.append(
        check(
            "QUAR-PERSISTED-BEFORE-HALT",
            {"quarantine_merged_before_halt_decision": True},
            {
                "quarantine_merged_before_halt_decision": bool(
                    run2["quarantine"]["persisted_before_halt_decision"]
                )
            },
            "the job merges the rejected rows into the quarantine table and only then compares the "
            "rate with the 5% threshold and raises, so a halted run leaves the operator the payloads "
            "that caused it while no invoice, line or credit application is written",
            quarantine_merge_metrics=idem_metrics.get(f"quarantine_{UNIT}"),
            halt_threshold_pct=SPEC["quarantine_halt_threshold_pct"],
            measured_quarantine_rate_pct=quar_pct,
        )
    )
    checks.append(
        check(
            "ANOM-SWALLOWED-EXCEPTION-SURFACED",
            {"partial_invoices_written": 0},
            {
                "partial_invoices_written": len(
                    [
                        r
                        for r in snap["invoice_rows"]
                        if r["_origin"] == "target-issue"
                        and (r["plan_fee"] is None or r["overage_amount"] is None
                             or r["tax_computed"] is None)
                    ]
                )
            },
            "every source path in this unit's lineage that swallows a failure is enumerated with its "
            "live exposure by the job run; no issued invoice may carry a NULL money column, because "
            "a tenant that hits one of those paths is quarantined instead",
            source_swallowed_paths=run2["swallowed_exceptions"]["source_swallowed_paths"],
            live_exposure=run2["swallowed_exceptions"]["live_exposure"],
            target_behaviour=run2["swallowed_exceptions"]["target_behaviour"],
            quarantined_rows=quar_rows,
            quarantine_by_source_table_and_reason=quar_by,
        )
    )

    checks.extend(transcript_checks(run2, snap, oracle, pinned_sha))

    anomalies = run2["anomaly_detections"]
    for aid in EXPECTED_ANOMALIES:
        det = anomalies.get(aid, {})
        checks.append(
            check(
                f"ANOMALY-{aid}",
                {"detected": True},
                {"detected": bool(det.get("detected"))},
                f"detector run by the job over ns = '{ns}': {det.get('detector', 'MISSING')}",
                evidence={k: v for k, v in det.items() if k not in ("detected", "detector")},
            )
        )

    failed = [c["id"] for c in checks if c["result"] == "fail"]
    actual_anomalies = [a for a in EXPECTED_ANOMALIES if anomalies.get(a, {}).get("detected")]
    zero_reason_exposure = [
        r
        for r in SPEC["quarantine_reasons"]
        if not any(k.endswith(r) for k in quar_by)
    ]
    unverified = [
        "Lakehouse Federation from the workspace to the OW_BILLING service is not reachable (wave 1 "
        "established this), so no single query joins source to target. Each side is measured "
        "independently — Oracle by a read-only session, the target by the SQL warehouse — and "
        "compared row by row here.",
        "The Oracle side of the parity comparison is compute_preview/fn_invoice_preview/"
        "sp_issue_invoice, with the pkg_rating.compute_rating call they depend on, re-expressed as "
        "read-only SQL evaluated by Oracle — not the PL/SQL package executed. Executing it would "
        "write INVOICES/INVOICE_LINES rows and burn CREDIT_NOTES down, mutating the estate; the six "
        "pinned transcripts are what tie the re-expression to the real engine.",
        "The source's re-issue burns credit twice: sp_issue_invoice recomputes g_credit from the "
        "balances its own first issue already reduced, so across two issues the notes are consumed "
        "by more than the credit the invoice finally grants. This port re-derives the same rows "
        "instead, so a rerun is a no-op (ACC-IDEM). The exposure is measured "
        f"({anomalies['ANOM-CREDIT-OVERAPPLY']['reissue_exposure']['credit_that_would_be_burned_again']}"
        " of credit across "
        f"{anomalies['ANOM-CREDIT-OVERAPPLY']['reissue_exposure']['invoices_that_would_burn_credit_again']}"
        " invoices) but the double burn itself is deliberately not reproduced: it is a divergence, "
        "declared here rather than hidden.",
        "Divergence — orphan invoice header on a failed issue: sp_issue_invoice INSERTs the INVOICES "
        "row before the line loop, so a tenant whose plan or usage line then raises (the D-19 "
        "NO_COVERING_PLAN case: NULL into INVOICE_LINES.description/.amount, both NOT NULL) leaves a "
        "zeroed header with no lines behind in the source. This port quarantines that tenant and "
        "writes no invoice at all, preferring a reject over a header whose money never landed. It "
        "becomes an invoices row-count delta of one row per affected tenant (source higher) as soon "
        "as quarantine is non-empty.",
        "CREDIT_NOTES is a bronze target, so this unit never writes the burnt-down balances back: "
        "the burn-down is recorded in ow_tp.silver.credit_applications, one row per (invoice, note "
        "visited), carrying remaining_before/applied_amount/remaining_after. The source's in-place "
        "UPDATE of CREDIT_NOTES.remaining_amount therefore has no target column, and the balances in "
        "ow_tp.bronze.credit_notes stay as the bronze units loaded them.",
        f"Quarantine reasons with zero live exposure on this population: {zero_reason_exposure}. "
        "Each is implemented and its exposure measured as zero, so the write path for those reasons "
        "is exercised by no row here — implemented and unverified, not proven. NUMERIC_OVERFLOW's "
        "guard is additionally probed on a synthetic value (QUAR-NUMERIC_OVERFLOW-REACHABLE).",
        "D-05/T4 (two-digit years resolving into the current century), D-06/BAD_DATE, D-25/"
        "ENC_INVALID and RECORD_SHORT/AMT_NON_NUMERIC are not reachable from this unit: invoicing "
        "reads typed DATE/TIMESTAMP/NUMBER columns out of bronze, so pkg_ow_util.f_str2dt and the "
        "delimited-record paths those codes describe are never called here. They belong to the "
        "bronze units that parse the flat files.",
        "sp_issue_invoice ends with a pkg_ow_util.log_msg autonomous-transaction audit write whose "
        "WHEN OTHERS THEN ROLLBACK discards failures silently. That audit trail is bronze_hist's "
        "target (BILLING_AUDIT_LOG), not this unit's, so no audit row is produced here and no audit "
        "parity is claimed.",
        "ANOM-ROWNUM-1 (the rating unit's nondeterministic ROWNUM <= 1 subscription pick) is inside "
        "the inline rating this unit recomputes. No tenant in this population has two covering "
        "subscriptions with the same starts_on, so the tie is not exercised; the target's ORDER BY "
        "starts_on DESC, id DESC tie-break (D-08) is implemented and unverified against a tie. The "
        "two picks compute_preview and compute_rating make disagree on "
        f"{run2['swallowed_exceptions']['live_exposure']['tenants_where_the_two_subscription_picks_disagree']}"
        " tenants here, and both are carried on the invoice row.",
        f"The ns = '{ns}' slice of the shared workspace is visible to other sessions holding the "
        "same PAT. This recon is re-runnable and every number is recomputed from the Delta targets "
        "after the second run, but it cannot prove that no other session wrote between the two runs. "
        "The MERGE/DELETE metrics behind the idempotency proof are attributed to commits this run "
        "produced (version > the target's pre-run version, and the commit's job.jobName is the job "
        "run named for this run's batch id \u2014 serverless rejects "
        "spark.databricks.delta.commitInfo.userMetadata, so the writing job run is the stamp), which "
        "excludes a foreign commit from the proof but not a foreign write from the row counts taken "
        "afterwards.",
        "Divergence — cross-table atomicity: sp_issue_invoice is one Oracle transaction over the "
        "header, its lines and the credit burn-down, while this port makes three independent Delta "
        "commits plus a scoped DELETE. Between the invoices commit and the invoice_lines commit a "
        "reader can therefore see a header without its lines, and between the lines commit and the "
        "credit_applications commit a header and lines without the applications that reduced them — "
        "a window of one commit each, on the order of seconds, closed by the next run because the "
        "retry re-derives the identical rows and converges on the same end state (ACC-IDEM, proven "
        "by the second-run metrics). Staged publication behind a batch marker is an estate-wide "
        "target-architecture decision for every silver and gold unit rather than something this unit "
        "invents for itself, so it is recorded here and carried centrally into the wave plan as a "
        "pre-cutover design item; it is not implemented in this unit.",
        "The stale credit-application removal path is proven by a targeted case "
        f"({stale_proof.get('status')}: one synthetic application planted on the target for an "
        "issued invoice under a note the recomputed sequence does not visit, then the unit run "
        "again), not by this population — a run over unchanged bronze produces the same applications "
        "every time, so no row here is naturally stale. ACC-CREDIT-RECONCILE carries the measured "
        "before/after counts.",
    ]

    return {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": now_iso(),
        "run_mode": "live",
        "recon_result": "green" if not failed else "red",
        "values_recomputed_from_target": True,
        "failed_checks": failed,
        "checks": checks,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idem_zero and counts_same and sums_same else "fail",
            "evidence": (
                f"run 1 = serverless run {run1['run_id']} (batch {run1['batch_id']}), run 2 = "
                f"serverless run {run2['run_id']} (batch {run2['batch_id']}), identical parameters "
                f"(ns={ns}, period {PERIOD_START}..{PERIOD_END}). Second-run Delta MERGE metrics: "
                f"{json.dumps(idem_metrics, sort_keys=True)}. Row counts after each run: "
                f"{json.dumps({'run1': run1['target_counts'], 'run2': run2['target_counts']}, sort_keys=True)}. "
                f"Parity checksums after each run: "
                f"{json.dumps({'run1': run1['checksums'], 'run2': run2['checksums']}, sort_keys=True)}"
            ),
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": actual_anomalies,
            "missing": [a for a in EXPECTED_ANOMALIES if a not in actual_anomalies],
            "unexpected": [a for a in anomalies if a not in EXPECTED_ANOMALIES],
            "detail": anomalies,
        },
        "unverified_paths": unverified,
        "swallowed_exceptions": run2["swallowed_exceptions"],
        "quarantine": run2["quarantine"],
        "provenance": {
            "source": {
                "system": "Oracle OW_BILLING (live)",
                "oracle_version": oracle["oracle_banner"],
                "db_name": os.getenv("DB_SERVICE", "FREEPDB1"),
                "schema": "OW_BILLING",
                "oracle_source_sha": oracle["oracle_source_sha"],
                "package": SPEC["source_artifact"],
                "entrypoints": SPEC["source_entrypoints"],
                "counts": src,
                "read_only": True,
                "batch_chain_executed": False,
            },
            "seeded_scale": seeded_scale(),
            "target": {
                "catalog": CATALOG,
                "schema": SCHEMA,
                "tables": [f"{CATALOG}.{SCHEMA}.{t}" for t in
                           ("invoices", "invoice_lines", "credit_applications",
                            f"quarantine_{UNIT}")],
                "bronze_inputs_read_only": run2["bronze_inputs"],
                "rating_input_policy": run2["rating_input_policy"],
                "compute": "serverless job compute for the notebook runs; pre-existing Serverless "
                "Starter Warehouse (565cd2fd713738c4) for the recon SQL. No cluster or warehouse was "
                "created.",
                "row_counts": snap["counts"],
                "money": snap["money"],
                "checksums": run2["checksums"],
                "column_types": snap["column_types"],
            },
            "period": {"start": PERIOD_START, "end": PERIOD_END},
            "job_runs": [
                {"batch_id": r["batch_id"], "run_id": r["run_id"],
                 "run_page_path": r.get("run_page_path")}
                for r in all_runs
            ],
            "baseline": {
                "transcripts": sorted(p.name for p in TRANSCRIPT_DIR.glob("INVOICE-*.json")),
                "pinned_sha_file": str(PINNED_SHA_FILE.relative_to(ROOT)),
                "note": "procs/transcripts/ (Postgres) is a cross-check set and is not the baseline",
            },
        },
    }


def stale_credit_removal_proof(dbx: Dbx, ns: str, batch_id: str) -> tuple[dict[str, Any], dict]:
    """A measured case for the credit-application reconciliation, not an argument that it works.

    This population never leaves a stale application behind: the recomputed sequence produces the
    same rows every time, which is what ACC-IDEM requires. So the case is manufactured on the target
    side only — one synthetic application is planted for an invoice this run issues, under a
    credit_note_id the sequence does not produce — and the unit is run again. A correct
    reconciliation removes exactly that row and leaves every real application, in this ns and in
    others, untouched. Nothing in the source is mutated and no other unit's table is touched.
    """
    ns_lit = sql_str(ns)
    tbl = f"{CATALOG}.{SCHEMA}.credit_applications"
    anchor = dbx.sql(
        f"""
        SELECT invoice_id, tenant_id FROM {tbl}
        WHERE ns = {ns_lit} ORDER BY invoice_id LIMIT 1
        """
    )
    if not anchor:
        return (
            {
                "status": "unreachable",
                "why": "no credit application exists in this ns to anchor the case to, so the "
                "removal path is declared unverified rather than claimed",
            },
            {},
        )
    invoice_id, tenant_id = str(anchor[0][0]), str(anchor[0][1])
    probe_id = f"stale-credit-probe-{batch_id}"
    probe_note = f"stale-credit-note-{batch_id}"

    def counts() -> tuple[int, int, int]:
        rows = dbx.sql(
            f"""
            SELECT (SELECT count(*) FROM {tbl} WHERE ns = {ns_lit}),
                   (SELECT count(*) FROM {tbl} WHERE ns = {ns_lit}
                     AND id = {sql_str(probe_id)}),
                   (SELECT count(*) FROM {tbl} WHERE ns <> {ns_lit})
            """
        )[0]
        return int(rows[0]), int(rows[1]), int(rows[2])

    dbx.sql(
        f"""
        INSERT INTO {tbl}
          (id, invoice_id, tenant_id, credit_note_id, seq_no, issued_on, bronze_remaining_amount,
           applied_by_other_invoices, remaining_before, credit_running_before, applied_amount,
           remaining_after, credit_running_after, skipped_by_exit_when,
           ns, _origin, _batch_id, _loaded_at)
        VALUES ({sql_str(probe_id)}, {sql_str(invoice_id)}, {sql_str(tenant_id)},
                {sql_str(probe_note)}, 99, TIMESTAMP '2026-01-01 00:00:00',
                CAST(10.00 AS DECIMAL(14,2)), CAST(0.00 AS DECIMAL(14,2)),
                CAST(10.00 AS DECIMAL(14,2)), CAST(10.00 AS DECIMAL(14,2)),
                CAST(10.00 AS DECIMAL(14,2)), CAST(0.00 AS DECIMAL(14,2)),
                CAST(0.00 AS DECIMAL(14,2)), false,
                {ns_lit}, 'target-issue', {sql_str(batch_id)}, current_timestamp())
        """
    )
    total_before, probe_before, other_ns_before = counts()
    run = run_notebook(dbx, ns, batch_id)
    total_after, probe_after, other_ns_after = counts()
    if probe_after:
        dbx.sql(f"DELETE FROM {tbl} WHERE ns = {ns_lit} AND id = {sql_str(probe_id)}")
    proof = {
        "status": "measured",
        "planted_row": {
            "id": probe_id,
            "invoice_id": invoice_id,
            "credit_note_id": probe_note,
            "applied_amount": "10.00",
            "why_stale": "the recomputed sequence for this invoice does not visit this note, so the "
                         "row is exactly the shape of an application left behind by a note that has "
                         "gone, a balance now zero, or a corrected input",
        },
        "applications_before_the_run": total_before,
        "applications_after_the_run": total_after,
        "planted_row_present_before_the_run": probe_before,
        "planted_row_present_after_the_run": probe_after,
        "real_applications_kept": total_after,
        "applications_in_other_namespaces_before": other_ns_before,
        "applications_in_other_namespaces_after": other_ns_after,
        "reconciliation": run["rebuild"]["credit_applications"],
        "batch_id": run["batch_id"],
        "run_id": run["run_id"],
    }
    return proof, run


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

    oracle = oracle_truth.snapshot(PERIOD_START, PERIOD_END, TAX_PROBE_AMOUNTS)
    print(
        f"[oracle] counts={oracle['source_counts']} invoices_computed={len(oracle['invoices'])} "
        f"credit_notes_visited={len(oracle['credit_burn'])}"
    )

    dbx = Dbx()
    deploy(dbx)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    run1 = run_notebook(dbx, ns, f"{stamp}a")
    print(f"[run a] {run1['run_id']} drivers={run1['drivers']} quar={run1['quarantine']['rate_pct']}%")
    if run1["quarantine"]["rate_pct"] > SPEC["quarantine_halt_threshold_pct"]:
        raise Halt(
            f"quarantine rate {run1['quarantine']['rate_pct']}% exceeds "
            f"{SPEC['quarantine_halt_threshold_pct']}%: halting the unit"
        )

    run2 = run_notebook(dbx, ns, f"{stamp}b")
    print(f"[run b] {run2['run_id']} merge={json.dumps(run2['merge_metrics'])}")
    if run2["quarantine"]["rate_pct"] > SPEC["quarantine_halt_threshold_pct"]:
        raise Halt(
            f"quarantine rate {run2['quarantine']['rate_pct']}% exceeds "
            f"{SPEC['quarantine_halt_threshold_pct']}%: halting the unit"
        )

    stale_proof, run3 = stale_credit_removal_proof(dbx, ns, f"{stamp}c")
    print(f"[run c] stale credit-application removal: {stale_proof['status']}")

    snap = target_snapshot(dbx, ns)
    issued_oracle = {
        tid: inv
        for tid, inv in oracle["invoices"].items()
        if inv["plan_fee"] is not None and inv["overage_amount"] is not None
    }
    parity = compare_invoices(issued_oracle, snap["invoice_rows"])
    burn = compare_burn(
        oracle["credit_burn"], snap["burn_rows"], snap["quarantined_driver_tenants"]
    )
    migrated_ids = {r["id"] for r in snap["invoice_rows"] if r["_origin"] == "source-migrated"}
    migrated = compare_migrated(
        [r for r in oracle["existing_invoices"] if r["id"] in migrated_ids], snap["invoice_rows"]
    )
    migrated_lines = compare_migrated_lines(oracle["existing_lines"], snap["line_rows"])
    issued_ids = {r["id"] for r in snap["invoice_rows"] if r["_origin"] == "target-issue"}
    expected_rows = {
        "issued": len(issued_oracle),
        "migrated": len([r for r in oracle["existing_invoices"] if r["id"] not in issued_ids]),
    }
    expected_rows["invoices"] = expected_rows["issued"] + expected_rows["migrated"]
    print(
        f"[parity] invoices differing={parity['rows_differing']}/{parity['rows_compared']} "
        f"burn differing={burn['rows_differing']}/{burn['rows_compared']} "
        f"migrated differing={migrated['rows_differing']}/{migrated['rows_compared']}"
    )

    report = build_report(
        ns, oracle, run1, run2, snap, parity, burn, migrated, migrated_lines, expected_rows,
        pinned_sha, [r for r in (run1, run2, run3) if r], stale_proof,
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
