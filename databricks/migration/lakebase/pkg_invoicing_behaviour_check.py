#!/usr/bin/env python3
"""Diff the converted billing.* invoicing entrypoints against the Oracle expectation file.

Unit p1-pkg-invoicing (U-23). The recon harness compares tables; a package entrypoint is not
a table, and the source is read-only so no Oracle view can expose one (P1-D9). This is the
behavioural half of the unit's evidence: it replays the scenarios captured from the Oracle
fixture by databricks/migration/transport/pkg_invoicing_expected_fixture.py against Lakebase
and reports every field that differs. It never reads Oracle.

The replay runs inside one transaction that is ROLLED BACK, so nothing this script does
survives: invoices, invoice_lines, credit_notes, the rating tables and the audit log keep the
rows the earlier waves loaded.

usage: python3 pkg_invoicing_behaviour_check.py --expected <file.json> --out <file.json>
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

INVOICE = """
SELECT id, tenant_id, period_id, issued_at, subtotal, tax, total, status_cd
  FROM billing.invoices WHERE id = %(invoice_id)s
"""

CREDIT_NOTES = """
SELECT id, tenant_id, issued_on, amount, remaining_amount
  FROM billing.credit_notes WHERE tenant_id = %(tenant_id)s ORDER BY issued_on, id
"""

AUDIT_AFTER = """
SELECT module, message FROM billing.billing_audit_log
 WHERE log_id > %(since)s ORDER BY log_id
"""

RATING_STATE = """
SELECT overage_amount FROM billing.rating_state
 WHERE tenant_id = %(tenant_id)s AND period_id = %(period_id)s
"""


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
    report = {"unit": "p1-pkg-invoicing", "kind": "behaviour-run-diff",
              "expected_source": expected["source"], "scenarios": {}}

    with psycopg.connect(dsn, autocommit=False) as conn:
        cur = conn.cursor()
        for name, want in expected["scenarios"].items():
            tenant_id = want["tenant_id"]
            params = (tenant_id, period_start, period_end)
            mismatches: list[str] = []

            # The ids sp_issue_invoice derives have to match Oracle's, or nothing else can.
            cur.execute("SELECT billing.f_md5_uuid(%s || to_char(%s::timestamp, "
                        "'YYYY-MM-DD'))", (tenant_id, period_start))
            period_id = cur.fetchone()[0]
            cur.execute("SELECT billing.f_md5_uuid(%s || 'invoice')", (period_id,))
            invoice_id = cur.fetchone()[0]
            diff("period_id", want["period_id"], period_id, mismatches)
            diff("invoice_id", want["invoice_id"], invoice_id, mismatches)

            cur.execute("SELECT * FROM billing.fn_invoice_preview(%s, %s, %s)", params)
            diff("preview", want["preview"], rows(cur), mismatches)
            diff("credit_notes_pre", want["credit_notes_pre"],
                 fetch(cur, CREDIT_NOTES, tenant_id=tenant_id), mismatches)

            if "invoice" in want:
                cur.execute("SELECT coalesce(max(log_id), 0) "
                            "FROM billing.billing_audit_log")
                since = cur.fetchone()[0]
                cur.execute("CALL billing.sp_issue_invoice(%s, %s, %s)", params)
                diff("invoice", want["invoice"],
                     fetch(cur, INVOICE, invoice_id=invoice_id), mismatches)
                cur.execute("SELECT * FROM billing.fn_invoice_lines(%s)", (invoice_id,))
                diff("lines", want["lines"], rows(cur), mismatches)
                diff("credit_notes_post", want["credit_notes_post"],
                     fetch(cur, CREDIT_NOTES, tenant_id=tenant_id), mismatches)
                # Oracle's log_msg is autonomous and its rows survive a rollback; here they
                # do not (declared divergence P1-D1a). The rows themselves, and their order,
                # are the behaviour being compared.
                diff("audit", want["audit"],
                     fetch(cur, AUDIT_AFTER, since=since), mismatches)
                # The explicit form of pkg_rating's g_overage_amount (P1-D4): the value
                # sp_issue_invoice read out of state has to be the usage line it billed.
                state = fetch(cur, RATING_STATE, tenant_id=tenant_id, period_id=period_id)
                usage_line = [ln for ln in want["preview"] if ln["line_type"] == "usage"]
                diff("rating_state_overage",
                     [{"overage_amount": usage_line[0]["amount"]}], state, mismatches)

                cur.execute("CALL billing.sp_issue_invoice(%s, %s, %s)", params)
                diff("invoice_rerun", want["invoice_rerun"],
                     fetch(cur, INVOICE, invoice_id=invoice_id), mismatches)
                cur.execute("SELECT * FROM billing.fn_invoice_lines(%s)", (invoice_id,))
                diff("lines_rerun", want["lines_rerun"], rows(cur), mismatches)
                diff("credit_notes_rerun", want["credit_notes_rerun"],
                     fetch(cur, CREDIT_NOTES, tenant_id=tenant_id), mismatches)

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
