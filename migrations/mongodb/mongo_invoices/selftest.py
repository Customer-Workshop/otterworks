#!/usr/bin/env python3
"""Exercise the transform paths the demo namespace's source data never hits.

The estate's current invoice lines all decode cleanly and all carry parseable
dates, so the invalid-encoding, invalid-date and NULL-attribution branches are
covered here instead of by the migration run. Pure transform checks: no Oracle
and no document store are touched.

Usage: migrations/mongodb/mongo_invoices/run.sh selftest
"""

from __future__ import annotations

import sys
from decimal import Decimal

import common
import migrate
import recon

FAILURES: list[str] = []


def check(name: str, expected, actual) -> None:
    if expected != actual:
        FAILURES.append(f"{name}: expected {expected!r}, got {actual!r}")


def raw_line(**overrides) -> dict:
    line = {
        "line_id": "line-1", "invoice_no": "DEMO-000000001", "invoice_id": "inv-1",
        "cust_id": "cust-1", "cust_no": "DEMO-00000001", "cust_name": "A Customer",
        "tenant_id": "tenant-1", "line_no": Decimal(3), "line_type_cd": Decimal(1),
        "item_desc": "Monthly platform fee", "qty": Decimal("2"),
        "unit_price": Decimal("10.5000"), "amount": Decimal("21.00"),
        "tax_amt": Decimal("1.73"), "invoice_dt": "14-FEB-24",
        "service_period": "012019-012020", "posted_yn": "Y",
        "gl_acct_csv": "40001,40002", "batch_no": Decimal(85559852),
        "src_system": "MAINFRAME",
    }
    line.update(overrides)
    return line


def transform(**overrides):
    quarantine = migrate.Quarantine("selftest")
    line = migrate.build_line("selftest", raw_line(**overrides), quarantine)
    return line, quarantine


def main() -> int:
    # dates: legacy two-digit years pivot, and text that is not a date raises
    check("date-2024", "2024-02-14",
          common.parse_legacy_date("14-FEB-24").date().isoformat())
    check("date-1999", "1999-12-01",
          common.parse_legacy_date("01-DEC-99").date().isoformat())
    check("date-null", None, common.parse_legacy_date(None))
    for bad in ("  -   -  ", "12-13-201", "29-FEB-23", "not-a-date", "31-FEB-24"):
        try:
            common.parse_legacy_date(bad)
            FAILURES.append(f"date-invalid: {bad!r} was accepted")
        except ValueError:
            pass

    # a line whose date is not a date is quarantined, never defaulted
    line, quarantine = transform(invoice_dt="12-13-201")
    check("invalid-date-not-migrated", None, line)
    check("invalid-date-reason", ["invalid_date"], [d["reason"] for d in quarantine.docs])

    # undecodable source bytes are quarantined with their raw bytes as hex
    undecodable = "fee \udcff\udcfe"
    check("undecodable-hex", "66656520fffe", common.undecodable_hex(undecodable))
    check("decodable-hex", None, common.undecodable_hex("Monthly platform fee"))
    line, quarantine = transform(item_desc=undecodable)
    check("invalid-encoding-not-migrated", None, line)
    check("invalid-encoding-reason", ["invalid_encoding"],
          [d["reason"] for d in quarantine.docs])
    check("invalid-encoding-raw-bytes", "66656520fffe",
          quarantine.docs[0]["detail"]["raw_bytes_hex"])

    # NULL money, quantity and foreign keys are quarantined, never zeroed
    for field, reason in (("amount", "null_amount"), ("tax_amt", "null_amount"),
                          ("qty", "null_quantity"), ("unit_price", "null_quantity"),
                          ("invoice_id", "null_foreign_key")):
        line, quarantine = transform(**{field: None})
        check(f"null-{field}-not-migrated", None, line)
        check(f"null-{field}-reason", [reason], [d["reason"] for d in quarantine.docs])

    # unexpected extra delimited content is tolerated and attributed
    line, quarantine = transform(gl_acct_csv="40001,not-an-account,40002")
    check("extra-fields-migrated-accounts", [40001, 40002], line["gl_accounts"])
    check("extra-fields-unattributed", ["not-an-account"],
          line["gl_accounts_unattributed"])
    check("extra-fields-reason", ["extra_delimited_fields"],
          [d["reason"] for d in quarantine.docs])
    check("extra-fields-attributed-amount", Decimal("21.00"),
          quarantine.docs[0]["parsed"]["amount"].to_decimal())

    # free text crosses byte-for-byte: no trimming, no normalization
    line, _ = transform(item_desc="  Late fee \u00a0\u2013 see notes  ")
    check("byte-transparency", "  Late fee \u00a0\u2013 see notes  ", line["item_desc"])

    # money stays exact and never passes through binary floating point
    line, _ = transform(unit_price=Decimal("0.0710"), qty=Decimal("3"),
                        amount=Decimal("0.21"))
    check("money-exact-amount", Decimal("0.21"), line["amount"].to_decimal())
    check("money-exact-unit-price", Decimal("0.0710"), line["unit_price"].to_decimal())

    # recon's own classification of a source row must match the dispositions the
    # migration applies, including the precedence between them
    header_ids = {"inv-1"}
    check("classify-embedded", None, recon.classify(raw_line(), header_ids))
    check("classify-null-fk", "null_foreign_key",
          recon.classify(raw_line(invoice_id=None), header_ids))
    check("classify-orphan", "orphan_no_header",
          recon.classify(raw_line(invoice_id="inv-missing"), header_ids))
    check("classify-orphan-outranks-null-amount", "orphan_no_header",
          recon.classify(raw_line(invoice_id="inv-missing", amount=None), header_ids))
    check("classify-header-unusable", "header_unusable",
          recon.classify(raw_line(), set(), {"inv-1"}))
    check("classify-null-fk-outranks-header", "null_foreign_key",
          recon.classify(raw_line(invoice_id=None), set(), {"inv-1"}))
    check("classify-null-amount", "null_amount",
          recon.classify(raw_line(tax_amt=None), header_ids))
    check("classify-null-quantity", "null_quantity",
          recon.classify(raw_line(qty=None), header_ids))
    check("classify-invalid-encoding", "invalid_encoding",
          recon.classify(raw_line(item_desc=undecodable), header_ids))
    check("classify-invalid-date", "invalid_date",
          recon.classify(raw_line(invoice_dt="12-13-201"), header_ids))

    # ids are derived, so the same source key always yields the same document id
    check("id-deterministic",
          common.invoice_doc_id("demo", "inv-1"),
          common.invoice_doc_id("demo", "inv-1"))
    check("id-namespace-scoped", True,
          common.invoice_doc_id("demo", "inv-1") !=
          common.invoice_doc_id("other", "inv-1"))

    for failure in FAILURES:
        print(f"FAIL {failure}")
    print(f"selftest: {'FAIL' if FAILURES else 'PASS'} ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
