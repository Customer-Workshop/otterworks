#!/usr/bin/env python3
"""Capture what Oracle pkg_invoicing does, from the fixture, as a JSON expectation file.

Unit p1-pkg-invoicing (U-23). The recon harness compares tables; a package entrypoint is not
a table, and the source is read-only so no Oracle view can expose one (P1-D9). This is the
behavioural half of the unit's evidence: run the legacy package over the fixture state,
record what it returns and what it writes, and let
databricks/migration/lakebase/pkg_invoicing_behaviour_check.py replay the same scenarios on
Lakebase and diff them. This script only reads Oracle and writes a JSON file; it never
touches the target.

FIXTURE ONLY. sp_issue_invoice writes (invoices, invoice_lines, credit_notes, the rating
tables and - through log_msg's autonomous transaction, which no rollback undoes - the audit
log), so this must never be pointed at the real estate. It takes the fixture DSN from
with_oracle_fixture.py and nothing else. Everything except the autonomous audit rows runs
inside a transaction that is rolled back, so the fixture is left as it was found.

usage: python3 pkg_invoicing_expected_fixture.py --out <file.json>
       run under databricks/migration/recon/with_oracle_fixture.py, which sets the env var.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path

import oracledb

oracledb.defaults.fetch_decimals = True

PERIOD_START = dt.datetime(2026, 2, 1)
PERIOD_END = dt.datetime(2026, 2, 28)

# Five scenarios over the deterministic baseline seed, chosen for the branches they reach:
#   credit_burn_down - two credit notes with the SAME issued_on, so the burn-down's
#                      `ORDER BY issued_on, id` tiebreak and the running-counter quirk
#                      (04_pkg_invoicing.sql:180-190) are both observable
#   burn_down_split  - two notes on different dates, the first smaller than the credit, so
#                      the second is only partly consumed: the quirk's arithmetic in full
#   tax_exempt       - tax_exempt_yn = 'Y': the DECODE branch that zeroes the tax, with an
#                      overage on top (2201 units against a 2000-unit plan)
#   rollover         - the tenant with prior rating periods, so sp_finalize_rating has
#                      history to roll over before the invoice is built
#   no_subscription  - an id with no subscription: NO_DATA_FOUND leaves the plan NULL, the
#                      tax goes NULL with it, and LEAST meets a NULL cap. Preview only: with
#                      no tenant row the invoice INSERT would fail on fk_inv_tenant, which is
#                      a constraint test, not a package test.
SCENARIOS = [
    {"name": "credit_burn_down", "tenant_id": "00000000-0000-0000-0000-000000000004",
     "issue": True},
    {"name": "burn_down_split", "tenant_id": "00000000-0000-0000-0000-000000000009",
     "issue": True},
    {"name": "tax_exempt", "tenant_id": "00000000-0000-0000-0000-000000000003",
     "issue": True},
    {"name": "rollover", "tenant_id": "00000000-0000-0000-0000-000000000001",
     "issue": True},
    {"name": "no_subscription", "tenant_id": "no-such-tenant", "issue": False},
]

INVOICE = """
SELECT id, tenant_id, period_id, issued_at, subtotal, tax, total, status_cd
  FROM invoices WHERE id = :invoice_id
"""

CREDIT_NOTES = """
SELECT id, tenant_id, issued_on, amount, remaining_amount
  FROM credit_notes WHERE tenant_id = :tenant_id ORDER BY issued_on, id
"""

AUDIT_AFTER = """
SELECT module, message FROM billing_audit_log
 WHERE log_id > :since ORDER BY log_id
"""


def jsonable(value):
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def rows(cur) -> list[dict]:
    cols = [d[0].lower() for d in cur.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def fetch(cur, sql, **binds) -> list[dict]:
    cur.execute(sql, binds)
    return rows(cur)


def preview(cur, tenant_id: str) -> list[dict]:
    out = cur.callfunc("pkg_invoicing.fn_invoice_preview", oracledb.CURSOR,
                       [tenant_id, PERIOD_START, PERIOD_END])
    return rows(out)


def lines(cur, invoice_id: str) -> list[dict]:
    out = cur.callfunc("pkg_invoicing.fn_invoice_lines", oracledb.CURSOR, [invoice_id])
    return rows(out)


def derived_invoice_id(cur, tenant_id: str) -> tuple[str, str]:
    """The ids sp_issue_invoice derives, computed the same way the package does."""
    cur.execute(
        "SELECT pkg_ow_util.f_md5_uuid(:t || TO_CHAR(:s, 'YYYY-MM-DD')) FROM dual",
        t=tenant_id, s=PERIOD_START)
    period_id = cur.fetchone()[0]
    cur.execute("SELECT pkg_ow_util.f_md5_uuid(:p || 'invoice') FROM dual", p=period_id)
    return period_id, cur.fetchone()[0]


def max_log_id(cur) -> int:
    cur.execute("SELECT NVL(MAX(log_id), 0) FROM billing_audit_log")
    return int(cur.fetchone()[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn-secret", default="OW_TP_ORACLE_FIXTURE",
                    help="ENV VAR NAME holding the fixture connection JSON, never a value")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    raw = os.environ.get(args.dsn_secret)
    if not raw:
        raise SystemExit(f"{args.dsn_secret} is not set; run under with_oracle_fixture.py")
    cfg = json.loads(raw)

    conn = oracledb.connect(user=cfg["user"], password=cfg["password"],
                            dsn=f"{cfg['host']}:{cfg['port']}/{cfg['service']}")
    out = {
        "source": "oracle-fixture",
        "unit": "p1-pkg-invoicing",
        "period_start": PERIOD_START.isoformat(sep=" ", timespec="seconds"),
        "period_end": PERIOD_END.isoformat(sep=" ", timespec="seconds"),
        "scenarios": {},
    }
    try:
        cur = conn.cursor()
        for scenario in SCENARIOS:
            tenant_id = scenario["tenant_id"]
            period_id, invoice_id = derived_invoice_id(cur, tenant_id)
            captured = {
                "tenant_id": tenant_id,
                "period_id": period_id,
                "invoice_id": invoice_id,
                "preview": preview(cur, tenant_id),
                "credit_notes_pre": fetch(cur, CREDIT_NOTES, tenant_id=tenant_id),
            }
            if scenario["issue"]:
                since = max_log_id(cur)
                cur.callproc("pkg_invoicing.sp_issue_invoice",
                             [tenant_id, PERIOD_START, PERIOD_END])
                captured["invoice"] = fetch(cur, INVOICE, invoice_id=invoice_id)
                captured["lines"] = lines(cur, invoice_id)
                captured["credit_notes_post"] = fetch(cur, CREDIT_NOTES,
                                                      tenant_id=tenant_id)
                # log_msg is autonomous, so these rows are committed and survive the
                # rollback below; they are read by log_id, not re-read after it.
                captured["audit"] = fetch(cur, AUDIT_AFTER, since=since)

                # Second issue of the same period: DUP_VAL_ON_INDEX on the header, the
                # delete-then-reinsert of the lines, and a second pass of the burn-down.
                cur.callproc("pkg_invoicing.sp_issue_invoice",
                             [tenant_id, PERIOD_START, PERIOD_END])
                captured["invoice_rerun"] = fetch(cur, INVOICE, invoice_id=invoice_id)
                captured["lines_rerun"] = lines(cur, invoice_id)
                captured["credit_notes_rerun"] = fetch(cur, CREDIT_NOTES,
                                                       tenant_id=tenant_id)
            out["scenarios"][scenario["name"]] = captured
            conn.rollback()     # each scenario starts from the state the fixture shipped

        conn.rollback()         # the fixture is left exactly as found
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"captured pkg_invoicing expectation for {len(out['scenarios'])} scenarios "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
