from datetime import date
from decimal import Decimal
import sys
from pathlib import Path

from oracle_custbill_extract import format_record, ns_batch_no, sort_rows

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services/legacy-billing/app"))
from reports import ns_batch_no as report_ns_batch_no


def test_batch_number_matches_reports():
    assert ns_batch_no("demo") == report_ns_batch_no("demo")
    assert ns_batch_no("rehearsal1") == report_ns_batch_no("rehearsal1")


def test_format_record_truncates_and_pads_legacy_columns():
    record = format_record({
        "invoice_id": "invoice-1",
        "cust_no": "CUSTOMER-TOO-LONG",
        "cust_name": "A" * 40,
        "period_end": date(2026, 2, 28),
        "total_amt": Decimal("12.345"),
        "record_type": "01",
    })
    assert len(record) == 65
    assert record[:10] == "CUSTOMER-T"
    assert record[10:40] == "A" * 30
    assert record[40:48] == "20260228"
    assert record[48:60] == "000000001235"
    assert record[60:] == "USD01"


def test_format_record_uses_credit_code_for_negative_amount():
    record = format_record({
        "invoice_id": "credit-1",
        "cust_no": "C1",
        "cust_name": "Credit",
        "period_end": "2026-03-01",
        "total_amt": "-2.50",
    })
    assert record[48:60] == "000000000250"
    assert record[63:] == "02"


def test_rows_are_sorted_by_period_customer_and_invoice():
    rows = [
        {"invoice_id": "b", "cust_no": "C2", "period_end": "2026-02-01"},
        {"invoice_id": "a", "cust_no": "C1", "period_end": "2026-02-02"},
        {"invoice_id": "a", "cust_no": "C1", "period_end": "2026-02-01"},
    ]
    assert [row["invoice_id"] for row in sort_rows(rows)] == ["a", "b", "a"]
