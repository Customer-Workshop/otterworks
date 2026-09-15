#!/usr/bin/env python3
"""Diff the converted billing.* rating entrypoints against the Oracle expectation file.

Unit p1-pkg-rating (U-22). The recon harness compares tables; a package entrypoint is not a
table, and the source is read-only so no Oracle view can expose one (P1-D9). This is the
behavioural half of the unit's evidence: it replays the scenarios captured from the Oracle
fixture by databricks/migration/transport/pkg_rating_expected_fixture.py against Lakebase and
reports every field that differs. It never reads Oracle.

The replay runs inside one transaction that is ROLLED BACK, so nothing this script does
survives: the rating tables keep the rows the earlier waves loaded.

usage: python3 pkg_rating_behaviour_check.py --expected <file.json> --out <file.json>
       run under with_lakebase_dsn.py, which sets OW_TP_LAKEBASE_DSN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path

import psycopg

RATING_PERIODS = """
SELECT id, tenant_id, period_start, period_end
  FROM billing.rating_periods WHERE tenant_id = %(tenant_id)s ORDER BY period_start
"""

RATING_RESULTS = """
SELECT rr.id, rr.period_id, rr.subscription_id, rr.used_units, rr.quota_units,
       rr.rollover_units, rr.billable_units, rr.overage_amount, rr.created_at
  FROM billing.rating_results rr
  JOIN billing.rating_periods rp ON rp.id = rr.period_id
 WHERE rp.tenant_id = %(tenant_id)s
 ORDER BY rp.period_start
"""

RATING_STATE = """
SELECT overage_amount FROM billing.rating_state
 WHERE tenant_id = %(tenant_id)s ORDER BY updated_at DESC LIMIT 1
"""

AUDIT_COUNT = "SELECT count(*) FROM billing.billing_audit_log WHERE module = 'RATING'"


def jsonable(value):
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, int) and not isinstance(value, bool):
        return format(Decimal(value), "f")
    return value


def rows(cur) -> list[dict]:
    cols = [d.name for d in cur.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def fetch(cur, sql, **params) -> list[dict]:
    cur.execute(sql, params)
    return rows(cur)


def diff(name: str, expected, actual, out: list[str]) -> None:
    if expected == actual:
        return
    out.append(f"{name}: oracle={json.dumps(expected)} lakebase={json.dumps(actual)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")

    expected = json.loads(args.expected.read_text())
    period_start = expected["period_start"]
    period_end = expected["period_end"]
    report = {"unit": "p1-pkg-rating", "kind": "behaviour-run-diff",
              "expected_source": expected["source"], "scenarios": {}}

    with psycopg.connect(dsn, autocommit=False) as conn:
        cur = conn.cursor()
        for name, want in expected["scenarios"].items():
            tenant_id = want["tenant_id"]
            params = (tenant_id, period_start, period_end)
            mismatches: list[str] = []

            cur.execute("SELECT * FROM billing.fn_usage_rating(%s, %s, %s)", params)
            diff("usage_rating", want["usage_rating"], rows(cur), mismatches)
            cur.execute("SELECT * FROM billing.fn_usage_summary(%s, %s, %s)", params)
            diff("usage_summary", want["usage_summary"], rows(cur), mismatches)
            diff("rating_periods_pre", want["rating_periods_pre"],
                 fetch(cur, RATING_PERIODS, tenant_id=tenant_id), mismatches)
            diff("rating_results_pre", want["rating_results_pre"],
                 fetch(cur, RATING_RESULTS, tenant_id=tenant_id), mismatches)

            if "overage_state" in want:
                cur.execute("SELECT count(*) FROM billing.billing_audit_log")
                audit_before = cur.fetchone()[0]
                cur.execute("CALL billing.sp_finalize_rating(%s, %s, %s)", params)
                diff("rating_periods_post", want["rating_periods_post"],
                     fetch(cur, RATING_PERIODS, tenant_id=tenant_id), mismatches)
                diff("rating_results_post", want["rating_results_post"],
                     fetch(cur, RATING_RESULTS, tenant_id=tenant_id), mismatches)
                # g_overage_amount on Oracle, a billing.rating_state row here (P1-D4).
                state = fetch(cur, RATING_STATE, tenant_id=tenant_id)
                diff("overage_state", [{"overage_amount": want["overage_state"]}], state,
                     mismatches)
                cur.execute("SELECT count(*) FROM billing.billing_audit_log")
                # compute_rating logs once and sp_finalize_rating logs once (D-009).
                diff("audit_rows_written", 2, cur.fetchone()[0] - audit_before, mismatches)

                cur.execute("CALL billing.sp_finalize_rating(%s, %s, %s)", params)
                diff("rating_periods_rerun", want["rating_periods_rerun"],
                     fetch(cur, RATING_PERIODS, tenant_id=tenant_id), mismatches)
                diff("rating_results_rerun", want["rating_results_rerun"],
                     fetch(cur, RATING_RESULTS, tenant_id=tenant_id), mismatches)

            report["scenarios"][name] = {
                "tenant_id": tenant_id,
                "status": "PASS" if not mismatches else "FAIL",
                "mismatches": mismatches,
            }
            conn.rollback()     # every scenario starts from the delivered state

        conn.rollback()         # nothing this check did is kept

    failed = [n for n, s in report["scenarios"].items() if s["status"] == "FAIL"]
    report["status"] = "PASS" if not failed else "FAIL"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    for name, scenario in report["scenarios"].items():
        print(f"{scenario['status']:4} {name}")
        for line in scenario["mismatches"]:
            print(f"       {line}")
    print(f"{report['status']} -> {args.out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
