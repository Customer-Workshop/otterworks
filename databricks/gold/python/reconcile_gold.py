#!/usr/bin/env python3
"""Reconcile every metric view against a direct query of the underlying Delta tables.

    python3 databricks/gold/python/reconcile_gold.py [--markdown] [--report PATH]

Each check runs the metric view and an independent statement that recomputes the same
number from the tables (and, where the source allows it, from silver rather than gold), then
compares them. A mismatch is a non-zero exit, so the job can gate on it.

`--report` writes the same result as a `*.recon.json` artifact, which is what the repo's
pre-PR self-check expects as evidence. Both sides are recomputed from the warehouse on every
run; no number in the report is copied from a previous one.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from apply_gold_sql import run
from databricks.sdk import WorkspaceClient

# (name, metric-view query, independent query recomputed from the tables)
CHECKS: list[tuple[str, str, str]] = [
    (
        "MRR total",
        "SELECT MEASURE(`MRR`) FROM ow_tp.gold.mv_arr_mrr",
        "SELECT SUM(mrr_amount) FROM ow_tp.gold.fct_subscription_mrr",
    ),
    (
        "ARR total",
        "SELECT MEASURE(`ARR`) FROM ow_tp.gold.mv_arr_mrr",
        # recomputed from the plan and subscription tables, not from the MRR fact
        "SELECT SUM(p.monthly_fee * 12) FROM ow_tp.gold.fct_subscription s "
        "JOIN ow_tp.gold.dim_plan p ON p.plan_id = s.plan_id "
        "WHERE s.status_cd = 10 AND s.starts_on <= current_timestamp() "
        "  AND (s.ends_on IS NULL OR s.ends_on >= current_timestamp())",
    ),
    (
        "Active subscriptions",
        "SELECT MEASURE(`Active Subscriptions`) FROM ow_tp.gold.mv_arr_mrr",
        "SELECT COUNT(*) FROM ow_tp.gold.fct_subscription WHERE status_cd = 10 "
        "AND starts_on <= current_timestamp() "
        "AND (ends_on IS NULL OR ends_on >= current_timestamp())",
    ),
    (
        "MRR: STARTER",
        "SELECT MEASURE(`MRR`) FROM ow_tp.gold.mv_arr_mrr WHERE `Plan` = 'STARTER'",
        "SELECT SUM(p.monthly_fee) FROM ow_tp.gold.fct_subscription s "
        "JOIN ow_tp.gold.dim_plan p ON p.plan_id = s.plan_id "
        "WHERE p.plan_code = 'STARTER' AND s.status_cd = 10 "
        "AND s.starts_on <= current_timestamp() "
        "AND (s.ends_on IS NULL OR s.ends_on >= current_timestamp())",
    ),
    (
        "MRR: GROWTH",
        "SELECT MEASURE(`MRR`) FROM ow_tp.gold.mv_arr_mrr WHERE `Plan` = 'GROWTH'",
        "SELECT SUM(p.monthly_fee) FROM ow_tp.gold.fct_subscription s "
        "JOIN ow_tp.gold.dim_plan p ON p.plan_id = s.plan_id "
        "WHERE p.plan_code = 'GROWTH' AND s.status_cd = 10 "
        "AND s.starts_on <= current_timestamp() "
        "AND (s.ends_on IS NULL OR s.ends_on >= current_timestamp())",
    ),
    (
        "MRR: SCALE",
        "SELECT MEASURE(`MRR`) FROM ow_tp.gold.mv_arr_mrr WHERE `Plan` = 'SCALE'",
        "SELECT SUM(p.monthly_fee) FROM ow_tp.gold.fct_subscription s "
        "JOIN ow_tp.gold.dim_plan p ON p.plan_id = s.plan_id "
        "WHERE p.plan_code = 'SCALE' AND s.status_cd = 10 "
        "AND s.starts_on <= current_timestamp() "
        "AND (s.ends_on IS NULL OR s.ends_on >= current_timestamp())",
    ),
    (
        "AR open balance",
        "SELECT MEASURE(`Open Balance`) FROM ow_tp.gold.mv_ar_ageing",
        # straight from silver: every issued/overdue invoice header
        "SELECT SUM(total_amt) FROM ow_tp.silver.invoice_header WHERE status_cd IN (20, 40)",
    ),
    (
        "AR open invoices",
        "SELECT MEASURE(`Open Invoices`) FROM ow_tp.gold.mv_ar_ageing",
        "SELECT COUNT(*) FROM ow_tp.silver.invoice_header WHERE status_cd IN (20, 40)",
    ),
    (
        "AR bucket 0-30",
        "SELECT MEASURE(`Open Balance`) FROM ow_tp.gold.mv_ar_ageing "
        "WHERE `Ageing Bucket` = '0-30'",
        # re-derived from the silver strings, independently of the gold bucket expression
        "SELECT SUM(h.total_amt) FROM ow_tp.silver.invoice_header h "
        "CROSS JOIN (SELECT MAX(CAST(invoice_dt_parsed AS DATE)) d "
        "            FROM ow_tp.silver.invoice_header WHERE status_cd IN (20,40)) a "
        "WHERE h.status_cd IN (20,40) "
        "AND DATEDIFF(a.d, CAST(TRY_TO_TIMESTAMP(h.due_dt,'dd-MMM-yy') AS DATE)) "
        "    BETWEEN 1 AND 30",
    ),
    (
        "AR bucket 31-60",
        "SELECT MEASURE(`Open Balance`) FROM ow_tp.gold.mv_ar_ageing "
        "WHERE `Ageing Bucket` = '31-60'",
        "SELECT SUM(h.total_amt) FROM ow_tp.silver.invoice_header h "
        "CROSS JOIN (SELECT MAX(CAST(invoice_dt_parsed AS DATE)) d "
        "            FROM ow_tp.silver.invoice_header WHERE status_cd IN (20,40)) a "
        "WHERE h.status_cd IN (20,40) "
        "AND DATEDIFF(a.d, CAST(TRY_TO_TIMESTAMP(h.due_dt,'dd-MMM-yy') AS DATE)) "
        "    BETWEEN 31 AND 60",
    ),
    (
        "AR bucket 61-90",
        "SELECT MEASURE(`Open Balance`) FROM ow_tp.gold.mv_ar_ageing "
        "WHERE `Ageing Bucket` = '61-90'",
        "SELECT SUM(h.total_amt) FROM ow_tp.silver.invoice_header h "
        "CROSS JOIN (SELECT MAX(CAST(invoice_dt_parsed AS DATE)) d "
        "            FROM ow_tp.silver.invoice_header WHERE status_cd IN (20,40)) a "
        "WHERE h.status_cd IN (20,40) "
        "AND DATEDIFF(a.d, CAST(TRY_TO_TIMESTAMP(h.due_dt,'dd-MMM-yy') AS DATE)) "
        "    BETWEEN 61 AND 90",
    ),
    (
        "AR bucket 90+",
        "SELECT MEASURE(`Open Balance`) FROM ow_tp.gold.mv_ar_ageing "
        "WHERE `Ageing Bucket` = '90+'",
        "SELECT SUM(h.total_amt) FROM ow_tp.silver.invoice_header h "
        "CROSS JOIN (SELECT MAX(CAST(invoice_dt_parsed AS DATE)) d "
        "            FROM ow_tp.silver.invoice_header WHERE status_cd IN (20,40)) a "
        "WHERE h.status_cd IN (20,40) "
        "AND DATEDIFF(a.d, CAST(TRY_TO_TIMESTAMP(h.due_dt,'dd-MMM-yy') AS DATE)) > 90",
    ),
    (
        "Overage amount",
        "SELECT MEASURE(`Overage Amount`) FROM ow_tp.gold.mv_overage",
        "SELECT SUM(overage_amount) FROM ow_tp.gold.fct_usage_period",
    ),
    (
        "Used units (from silver)",
        "SELECT MEASURE(`Used Units`) FROM ow_tp.gold.mv_overage",
        "SELECT SUM(units) FROM ow_tp.silver.usage_events",
    ),
    (
        "Storage units (from silver)",
        "SELECT MEASURE(`Storage Units`) FROM ow_tp.gold.mv_storage_cost",
        "SELECT SUM(units) FROM ow_tp.silver.usage_events WHERE kind_cd = 2",
    ),
    (
        "Storage cost rows cover the same overage",
        "SELECT MEASURE(`Period Overage`) FROM ow_tp.gold.mv_storage_cost",
        "SELECT SUM(overage_amount) FROM ow_tp.gold.fct_usage_period",
    ),
]


def scalar(w: WorkspaceClient, sql: str) -> Decimal | None:
    rows = run(w, sql, {})
    if not rows or rows[0][0] is None:
        return None
    return Decimal(str(rows[0][0]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--report", type=Path, help="write a *.recon.json artifact here")
    args = ap.parse_args(argv)

    w = WorkspaceClient()
    results = []
    failed = 0
    for name, mv_sql, direct_sql in CHECKS:
        a, b = scalar(w, mv_sql), scalar(w, direct_sql)
        ok = a == b
        failed += 0 if ok else 1
        results.append((name, a, b, ok))

    if args.markdown:
        print("| check | metric view | direct Delta query | match |")
        print("|---|---:|---:|---|")
        for name, a, b, ok in results:
            print(f"| {name} | {a} | {b} | {'yes' if ok else 'NO'} |")
    else:
        for name, a, b, ok in results:
            print(f"{'ok ' if ok else 'FAIL'} {name}: view={a} direct={b}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "kind": "recon-report",
            "unit": "ow_tp_finance_gold",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tolerance": "exact",
            "verdict": "pass" if not failed else "fail",
            "checks": [{"check": name, "metric_view": str(a), "direct_query": str(b),
                        "match": ok} for name, a, b, ok in results],
        }, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
