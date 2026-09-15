#!/usr/bin/env python3
"""Recompute the dunning-risk recon report from the target, including a real rerun.

Every number in evidence/ow_tp_dunning_risk.recon.json is read back out of Databricks and
Lakebase by this program. None of it is copied from the numbers that were on screen while
the SQL was being written, which is the failure mode the pre-PR self-check is aimed at.

Idempotency is proved rather than asserted: the five derived tables are digested, all six SQL
files are re-executed, and the tables are digested again. The digest excludes `built_at`,
which is `current_timestamp()` and is expected to move; everything else must not.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set, and
OW_TP_LAKEBASE_DSN supplied by with_lakebase_dsn.py for the Lakebase checks):

  python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w0 \\
      -- python3 databricks/scoring/dunning_risk/emit_recon.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

WAREHOUSE = "565cd2fd713738c4"
SQL_DIR = Path(__file__).parent / "sql"
OUT = Path(__file__).parent / "evidence" / "ow_tp_dunning_risk.recon.json"

DERIVED = [
    "ow_tp.silver.dunning_risk_features_invoice",
    "ow_tp.silver.dunning_risk_features_account",
    "ow_tp.gold.dunning_risk_rules",
    "ow_tp.gold.dunning_risk_invoice",
    "ow_tp.gold.dunning_risk_account",
]

LAKEBASE_TABLES = [
    ("billing.dunning_risk_rules", "ow_tp.gold.dunning_risk_rules", None),
    ("billing.dunning_risk_invoice", "ow_tp.gold.dunning_risk_invoice", None),
    ("billing.dunning_risk_account", "ow_tp.gold.dunning_risk_account",
     "risk_band <> 'NO_OPEN_ITEMS'"),
]

_HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
_TOKEN: str | None = None


def token() -> str:
    global _TOKEN
    if _TOKEN is None:
        resp = requests.post(
            f"{_HOST}/oidc/v1/token",
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            auth=(os.environ["DATABRICKS_CLIENT_ID"],
                  os.environ["DATABRICKS_CLIENT_SECRET"]),
            timeout=60)
        resp.raise_for_status()
        _TOKEN = resp.json()["access_token"]
    return _TOKEN


def sql(statement: str, params: dict[str, str] | None = None) -> list[list]:
    headers = {"Authorization": f"Bearer {token()}"}
    body = {"warehouse_id": WAREHOUSE, "statement": statement, "wait_timeout": "50s",
            "format": "JSON_ARRAY", "disposition": "INLINE"}
    if params:
        body["parameters"] = [{"name": k, "value": v} for k, v in params.items()]
    resp = requests.post(f"{_HOST}/api/2.0/sql/statements", headers=headers, json=body,
                         timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    while payload["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3)
        payload = requests.get(f"{_HOST}/api/2.0/sql/statements/{payload['statement_id']}",
                               headers=headers, timeout=60).json()
    if payload["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"{statement[:80]}: {payload['status']}")
    return payload.get("result", {}).get("data_array", []) or []


def digest(table: str) -> dict:
    """Row count and an order-independent content hash, ignoring the build timestamp."""
    # crc32, not xxhash64: summing 64-bit hashes over 18k rows overflows a bigint
    rows = sql(
        "SELECT count(*), coalesce(sum(crc32(to_json(struct(t.*)))), 0) "
        f"FROM (SELECT * EXCEPT (built_at) FROM {table}) t")
    return {"rows": int(rows[0][0]), "hash": str(rows[0][1])}


def check(check_id: str, expected, actual, source: str) -> dict:
    return {"id": check_id, "expected": expected, "actual": actual,
            "source_of_truth": source,
            "result": "pass" if str(expected) == str(actual) else "fail"}


def main() -> int:
    checks: list[dict] = []

    # ---- source-vs-target population ---------------------------------------------------
    src_invoices = int(sql("SELECT count(*) FROM ow_tp.silver.invoice_header")[0][0])
    checks.append(check("features_invoice_covers_every_migrated_invoice", src_invoices,
                        int(sql("SELECT count(*) FROM "
                                "ow_tp.silver.dunning_risk_features_invoice")[0][0]),
                        "ow_tp.silver.invoice_header"))

    src_accounts = int(sql("SELECT count(*) FROM ow_tp.bronze.customer_master")[0][0])
    checks.append(check("features_account_covers_every_billing_account", src_accounts,
                        int(sql("SELECT count(*) FROM "
                                "ow_tp.silver.dunning_risk_features_account")[0][0]),
                        "ow_tp.bronze.customer_master"))

    src_open = int(sql("SELECT count(*) FROM ow_tp.silver.invoice_header "
                       "WHERE status_cd IN (20, 40)")[0][0])
    checks.append(check("scored_invoices_equal_open_invoices", src_open,
                        int(sql("SELECT count(*) FROM "
                                "ow_tp.gold.dunning_risk_invoice")[0][0]),
                        "ow_tp.silver.invoice_header status_cd IN (20,40)"))

    # ---- the score stays inside its declared range and bands ---------------------------
    checks.append(check("risk_score_within_0_100", 0,
                        int(sql("SELECT count(*) FROM ow_tp.gold.dunning_risk_invoice "
                                "WHERE risk_score < 0 OR risk_score > 100")[0][0]),
                        "ow_tp.gold.dunning_risk_invoice"))
    checks.append(check("risk_band_matches_risk_score", 0,
                        int(sql("""
        SELECT count(*) FROM ow_tp.gold.dunning_risk_invoice
         WHERE risk_band <> CASE WHEN risk_band = 'EXEMPT' THEN 'EXEMPT'
                                 WHEN risk_score >= 60 THEN 'CRITICAL'
                                 WHEN risk_score >= 40 THEN 'HIGH'
                                 WHEN risk_score >= 20 THEN 'MEDIUM'
                                 ELSE 'LOW' END""")[0][0]),
                        "ow_tp.gold.dunning_risk_invoice"))

    # the score must be the sum of the points of the rules it names, with nothing else added
    checks.append(check("risk_score_equals_sum_of_named_rule_points", 0,
                        int(sql("""
        WITH expanded AS (
          SELECT i.invoice_id, i.risk_score, i.risk_band,
                 explode_outer(i.reason_codes) AS code
            FROM ow_tp.gold.dunning_risk_invoice i),
        summed AS (
          SELECT e.invoice_id, max(e.risk_score) AS risk_score, max(e.risk_band) AS risk_band,
                 coalesce(sum(r.points), 0) AS expected
            FROM expanded e
            LEFT JOIN ow_tp.gold.dunning_risk_rules r ON r.rule_id = e.code
           GROUP BY e.invoice_id)
        SELECT count(*) FROM summed
         WHERE risk_band <> 'EXEMPT'
           AND risk_score <> greatest(0, least(100, expected))""")[0][0]),
                        "ow_tp.gold.dunning_risk_rules"))

    checks.append(check("every_reason_code_resolves_to_a_rule", 0,
                        int(sql("""
        SELECT count(*) FROM (
          SELECT explode(reason_codes) AS code FROM ow_tp.gold.dunning_risk_invoice) c
         WHERE NOT EXISTS (SELECT 1 FROM ow_tp.gold.dunning_risk_rules r
                            WHERE r.rule_id = c.code)""")[0][0]),
                        "ow_tp.gold.dunning_risk_rules"))

    # ---- missing coverage is NULL, never a zero that reads as good news ----------------
    checks.append(check("unavailable_features_are_null_not_zero", 0,
                        int(sql("""
        SELECT count(*) FROM ow_tp.silver.dunning_risk_features_invoice
         WHERE prior_dunning_attempts IS NOT NULL OR open_credit_note_amt IS NOT NULL
            OR plan_tier_cd IS NOT NULL OR usage_trend_ratio IS NOT NULL""")[0][0]),
                        "ow_tp.silver.dunning_risk_features_invoice"))
    checks.append(check("every_scored_row_declares_its_unscored_signals", 0,
                        int(sql("SELECT count(*) FROM ow_tp.gold.dunning_risk_invoice "
                                "WHERE unscored_signals IS NULL "
                                "OR size(unscored_signals) = 0")[0][0]),
                        "ow_tp.gold.dunning_risk_invoice"))

    # ---- the score takes no action -----------------------------------------------------
    checks.append(check("no_scored_row_is_outside_the_legacy_dunning_population",
                        0,
                        int(sql("SELECT count(*) FROM ow_tp.gold.dunning_risk_invoice "
                                "WHERE status_cd NOT IN (20, 40)")[0][0]),
                        "ow_tp.gold.dunning_risk_invoice"))

    # ---- backtest, recomputed from the target ------------------------------------------
    backtest = {f"{group}:{metric}:{population}": {"n": int(n), "value": float(value)}
                for group, metric, population, n, value in
                sql("SELECT metric_group, metric, population, n, value "
                    "FROM ow_tp.gold.dunning_risk_backtest")}
    auc = backtest["discrimination:auc:closed_2021_plus"]["value"]
    checks.append({
        "id": "backtest_auc_out_of_time",
        "expected": "no claim of predictive lift (0.5 is chance)",
        "actual": round(auc, 4),
        "source_of_truth": "ow_tp.gold.dunning_risk_backtest",
        "result": "pass" if abs(auc - 0.5) < 0.05 else "fail",
    })

    bands = {k.split(":")[1]: v for k, v in backtest.items()
             if k.startswith("band_outcome:") and k.endswith(":closed_all")}

    # ---- idempotency: digest, rerun everything, digest again ---------------------------
    before = {t: digest(t) for t in DERIVED}
    for path in sorted(SQL_DIR.glob("*.sql")):
        statement = path.read_text()
        sql(statement, {"as_of": ""} if ":as_of" in statement else None)
    after = {t: digest(t) for t in DERIVED}
    idempotent = before == after
    for table in DERIVED:
        checks.append(check(f"idempotent:{table}", before[table], after[table],
                            "digest of the table before and after a full rerun"))

    # ---- Lakebase, read back from the branch -------------------------------------------
    lakebase_checks_ran = False
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if dsn:
        import psycopg

        lakebase_checks_ran = True
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_schema()")
            database, schema = cur.fetchone()
            checks.append(check("lakebase_database", "ow_tp", database, "Lakebase"))
            for target, gold, predicate in LAKEBASE_TABLES:
                expected_sql = f"SELECT count(*) FROM {gold}"
                if predicate:
                    expected_sql += f" WHERE {predicate}"
                expected = int(sql(expected_sql)[0][0])
                cur.execute(f"SELECT count(*) FROM {target}")
                checks.append(check(f"lakebase_rows:{target}", expected, cur.fetchone()[0],
                                    f"{target} on branch mig-p1-w0"))
            # the constraints the DDL claims, read back from the catalogue rather than
            # from the file that was applied
            cur.execute("""
                SELECT conname FROM pg_constraint
                 WHERE conrelid IN ('billing.dunning_risk_invoice'::regclass,
                                    'billing.dunning_risk_account'::regclass,
                                    'billing.dunning_risk_rules'::regclass)
                 ORDER BY conname""")
            present = [r[0] for r in cur.fetchall()]
            for expected_constraint in ("ck_dunning_risk_account_score",
                                        "ck_dunning_risk_invoice_band",
                                        "ck_dunning_risk_invoice_score",
                                        "pk_dunning_risk_account",
                                        "pk_dunning_risk_invoice",
                                        "pk_dunning_risk_rules"):
                checks.append(check(f"lakebase_constraint:{expected_constraint}", True,
                                    expected_constraint in present, "pg_constraint"))
            cur.execute("""
                SELECT count(*) FROM information_schema.columns
                 WHERE table_schema = 'billing'
                   AND table_name LIKE 'dunning_risk%'
                   AND data_type = 'timestamp with time zone'""")
            checks.append(check("lakebase_no_timestamptz", 0, cur.fetchone()[0],
                                "information_schema.columns"))

    # ---- anomalies this unit surfaces rather than repairs -------------------------------
    due_before = int(sql("SELECT count(*) FROM ow_tp.silver.dunning_risk_features_invoice "
                         "WHERE due_before_invoice_dt")[0][0])
    tenant_overlap = int(sql("""
        SELECT count(*) FROM (SELECT DISTINCT tenant_id FROM ow_tp.silver.usage_events) u
         JOIN (SELECT DISTINCT tenant_id FROM ow_tp.silver.invoice_header) i
           ON u.tenant_id = i.tenant_id""")[0][0])
    thin_history = int(sql("SELECT count(*) FROM ow_tp.silver.dunning_risk_features_invoice "
                           "WHERE prior_overdue_rate IS NULL")[0][0])

    detected = []
    if due_before > 0:
        detected.append("due_dt_before_invoice_dt")
    if tenant_overlap == 0:
        detected.append("tenant_key_space_disjoint")
    if thin_history > 0:
        detected.append("payment_lateness_history_mostly_absent")
    if abs(auc - 0.5) < 0.05:
        detected.append("non_aging_signals_do_not_discriminate")
    expected_set = ["due_dt_before_invoice_dt", "tenant_key_space_disjoint",
                    "payment_lateness_history_mostly_absent",
                    "non_aging_signals_do_not_discriminate"]

    report = {
        "kind": "recon-report",
        "unit": "ow_tp_dunning_risk",
        "namespace": "ow_tp",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_mode": "live",
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": ("all six SQL files re-executed between two digests of the five "
                         "derived tables; row counts and content hashes (excluding "
                         "built_at) unchanged"),
        },
        "planted_anomaly_detections": {
            "expected_set": expected_set,
            "actual_set": detected,
            "missing": [a for a in expected_set if a not in detected],
            "unexpected": [a for a in detected if a not in expected_set],
        },
        "observations": {
            "due_dt_before_invoice_dt_rows": due_before,
            "usage_to_invoice_tenant_overlap": tenant_overlap,
            "invoices_without_payment_lateness_history": thin_history,
            "score_distribution_open_invoices": {
                band: int(n) for band, n in
                sql("SELECT risk_band, count(*) FROM ow_tp.gold.dunning_risk_invoice "
                    "GROUP BY risk_band")},
            "backtest": backtest,
            "backtest_band_outcome_closed_all": bands,
        },
        "unverified_paths": [
            "The score was never backtested against a dunning outcome. billing.dunning_attempts holds one row on Lakebase, on a tenant key space that does not intersect the invoice history, so 'did the dunning attempt recover the money' is untestable here. The label used is 'the invoice ended status 40'.",
            "prior_overdue_rate reads the current status of earlier invoices because no invoice status history was migrated, so the backtest can see outcomes that were not knowable at the time. It flatters the score and the score still does not discriminate.",
            "credit_hold_yn, past_due_amt and credit_limit_amt are today's values on the billing master, not their values at invoice time. Same direction of bias.",
            "Requested features not built: previous dunning attempts and their outcomes, credit notes, and plan. Their sources reached Lakebase but not Delta and are on the disjoint tenant key space. usage trend was not built for the same key reason. All four are NULL columns carrying the reason, not defaults.",
            "The Lakebase publish is not a task in the Lakeflow job. It runs through with_lakebase_dsn.py, which checks the branch against .migration/allowed_targets.json in the repo checkout; wiring it into the job would mean minting credentials in the workspace outside that check. The job was therefore verified end to end for the six Delta tasks only.",
            "The job has never been run. It was created PAUSED and its task graph, retries and warehouse were read back from the Jobs API, but no run has executed through the scheduler; the six statements were executed directly against the warehouse instead.",
            "No foreign key from billing.dunning_risk_invoice to billing.invoices. The three invoices on this branch are on the other key space, so the constraint would fail on load. Structure was verified by reading pg_constraint; referential integrity to the OLTP invoice table was not established.",
            "Lakebase writes were exercised on branch mig-p1-w0 only. Nothing in this change was run against Lakebase production, and the behaviour of these tables there is unverified.",
            "tenure_days is measured from the account's first migrated invoice. SIGNUP_DT is a DD-MON-YY string whose century is ambiguous, so it was not parsed and true tenure is unverified.",
            "The 14/28/56/84 aging thresholds are multiples of the one interval the legacy estate declares (pkg_dunning.sp_suspend_overdue). They were not fitted and their calibration against recovery rates is unverified.",
        ],
    }
    if not lakebase_checks_ran:
        report["unverified_paths"].insert(
            0, "Lakebase checks were skipped: OW_TP_LAKEBASE_DSN was not present, so the "
               "published tables and their constraints were not read back in this run.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    failed = [c["id"] for c in checks if c["result"] == "fail"]
    print(f"wrote {OUT} ({len(checks)} checks, {len(failed)} failed)")
    for check_id in failed:
        print(f"  FAILED {check_id}")
    return 1 if failed or not idempotent else 0


if __name__ == "__main__":
    raise SystemExit(main())
