"""Offline guards for the invoices loader's preflight, orphan handling, and line shaping.

These cover the ways the load can destroy or silently drop data rather than merely get it
wrong: clearing the target for an empty source, dropping a header column the mapping does not
carry, and losing the lines that belong to no invoice. All run against fakes — no Oracle, no
Atlas.
"""
import decimal
import sys
from pathlib import Path

import pytest
from bson.decimal128 import Decimal128

sys.path.insert(0, str(Path(__file__).resolve().parent))

from invoices_load import (
    assert_source_slice,
    fetch_lines,
    line_document,
    line_quarantine_document,
    load,
    orphan_document,
)

CONVENTIONS = Path(__file__).resolve().parents[2] / ".migration" / "01_conventions.md"

HEADER_COLUMNS = ["INVOICE_ID", "INVOICE_NO", "CUST_ID", "TENANT_ID", "INVOICE_DT", "DUE_DT",
                  "STATUS_CD", "TOTAL_AMT", "BATCH_NO"]

LINE_ROW = {
    "LINE_ID": "L-1", "LINE_NO": 1, "LINE_TYPE_CD": 1, "ITEM_DESC": "Seat licence",
    "QTY": decimal.Decimal("2.000"), "UNIT_PRICE": decimal.Decimal("15.5000"),
    "AMOUNT": decimal.Decimal("31.00"), "TAX_AMT": decimal.Decimal("2.48"),
    "SERVICE_PERIOD": "012024-012024", "POSTED_YN": "Y ", "SRC_SYSTEM": "MF",
    "BATCH_NO": 85559852, "INVOICE_NO": "INV-1", "CUST_ID": "C-1", "CUST_NO": "1001",
    "CUST_NAME": "Acme", "TENANT_ID": "T-1", "INVOICE_DT": "05-JAN-24",
    "GL_ACCT_CSV": "4000,4010",
}


class FakeCursor:
    """Answers the preflight queries, then the line query, in the order the loader issues
    them."""

    def __init__(self, header_count=18750, catalog=None, lines=()):
        self._header_count = header_count
        self._catalog = catalog if catalog is not None else [(c,) for c in HEADER_COLUMNS]
        self._lines = list(lines)
        self._rows = []
        self._result = None

    def execute(self, sql, **_):
        if sql.startswith("SELECT COUNT(*)"):
            self._result = (self._header_count,)
        elif "all_tab_columns" in sql:
            self._rows = list(self._catalog)
        else:
            self._rows = list(self._lines)

    def fetchone(self):
        return self._result

    def __iter__(self):
        return iter(self._rows)


def line_row(**overrides):
    """A line as `fetch_lines` reads it: invoice id, the mapped columns, header-present flag."""
    row = dict(LINE_ROW)
    has_header = overrides.pop("has_header", 1)
    row.update(overrides)
    from invoices_load import LINE_FIELDS
    return tuple([row["INVOICE_ID_REF"]] + [row[c] for c, _, _ in LINE_FIELDS] + [has_header])


def test_preflight_accepts_a_populated_batch_whose_columns_are_all_mapped():
    assert assert_source_slice(FakeCursor(), 85559852, set(HEADER_COLUMNS)) == 18750


def test_preflight_refuses_an_empty_batch_before_touching_the_target():
    with pytest.raises(SystemExit, match="no rows for BATCH_NO"):
        assert_source_slice(FakeCursor(header_count=0), 85559852, set(HEADER_COLUMNS))


def test_preflight_refuses_a_header_column_the_mapping_does_not_carry():
    cursor = FakeCursor(catalog=[(c,) for c in HEADER_COLUMNS] + [("SETTLED_DT",)])
    with pytest.raises(SystemExit, match="SETTLED_DT"):
        assert_source_slice(cursor, 85559852, set(HEADER_COLUMNS))


def test_a_line_whose_header_is_missing_is_quarantined_not_embedded():
    cursor = FakeCursor(lines=[
        line_row(INVOICE_ID_REF="INV-A", LINE_ID="L-1"),
        line_row(INVOICE_ID_REF="INV-GONE", LINE_ID="L-2", has_header=0),
    ])
    by_invoice, orphans, quarantine = fetch_lines(cursor, 85559852)
    assert quarantine == []

    assert [line["line_id"] for line in by_invoice["INV-A"]] == ["L-1"]
    assert "INV-GONE" not in by_invoice
    assert [o["line"]["line_id"] for o in orphans] == ["L-2"]

    record = orphan_document(orphans[0], "demo")
    assert record["reason"] == "orphan_invoice_line"
    assert record["_id"] == "demo:L-2"
    # The line itself is carried: there is no document to point at.
    assert record["line"]["amount"] == Decimal128("31.00")


def test_line_money_is_decimal128_and_the_legacy_text_is_preserved():
    line, bad_date = line_document(dict(LINE_ROW, INVOICE_ID="INV-A"))
    assert bad_date is None
    assert line["amount"] == Decimal128("31.00")
    assert line["unit_price"] == Decimal128("15.5000")
    assert line["qty"] == Decimal128("2.000")
    assert line["legacy"]["invoice_dt"] == "05-JAN-24"
    assert line["legacy"]["gl_acct_csv"] == "4000,4010"
    assert line["invoice_at"].isoformat() == "2024-01-05T00:00:00+00:00"
    # CHAR pads to its width; VARCHAR2 blanks are data, so only this column is stripped.
    assert line["posted_yn"] == "Y"


def test_an_unparseable_line_date_is_quarantined_and_the_raw_value_kept():
    line, bad_date = line_document(dict(LINE_ROW, INVOICE_ID="INV-A", INVOICE_DT="31-FEB-24"))
    assert line["legacy"]["invoice_dt"] == "31-FEB-24"
    assert "invoice_at" not in line

    record = line_quarantine_document(bad_date, "demo")
    assert record["reason"] == "unparseable_legacy_date"
    assert record["raw_value"] == "31-FEB-24"
    # Distinct from the orphan record's `demo:<line id>`, so a line can raise both.
    assert record["_id"] == "demo:L-1:INVOICE_DT"


def test_a_blank_line_date_is_neither_typed_nor_quarantined():
    line, bad_date = line_document(dict(LINE_ROW, INVOICE_ID="INV-A", INVOICE_DT="  -   -  "))
    assert line["legacy"]["invoice_dt"] == "  -   -  "
    assert "invoice_at" not in line
    assert bad_date is None


def test_punctuation_that_is_not_the_estates_blank_date_is_quarantined():
    for raw in ["--", "//", "-", "  -  ", " - - ", "   -   -   ", "N/A"]:
        _, bad_date = line_document(dict(LINE_ROW, INVOICE_ID="INV-A", INVOICE_DT=raw))
        assert bad_date is not None, raw


def test_an_embedded_line_with_a_bad_date_is_still_embedded_and_reported():
    cursor = FakeCursor(lines=[line_row(INVOICE_ID_REF="INV-A", LINE_ID="L-1",
                                        INVOICE_DT="31-FEB-24")])
    by_invoice, orphans, quarantine = fetch_lines(cursor, 85559852)
    assert [line["line_id"] for line in by_invoice["INV-A"]] == ["L-1"]
    assert orphans == []
    assert [(q["line_id"], q["reason"]) for q in quarantine] == [
        ("L-1", "unparseable_legacy_date")]


def test_an_orphan_with_a_bad_date_is_reported_once_as_an_orphan():
    cursor = FakeCursor(lines=[line_row(INVOICE_ID_REF="INV-GONE", LINE_ID="L-2",
                                        INVOICE_DT="31-FEB-24", has_header=0)])
    _, orphans, quarantine = fetch_lines(cursor, 85559852)
    assert len(orphans) == 1
    assert quarantine == []


@pytest.mark.parametrize("target_db,quarantine_db", [
    ("ow_tp_billing_demo", "ow_tp_demo_quarantine"),
    ("ow_tp_demo", "ow_tp_mongodb_demo_quarantine"),
])
def test_a_database_outside_the_conventions_record_is_refused(target_db, quarantine_db):
    with pytest.raises(SystemExit, match="not the database designated"):
        load("demo", "OW_BILLING_SOURCE_DSN", "MONGODB_ATLAS_URI", target_db, quarantine_db,
             conventions_path=CONVENTIONS)


@pytest.mark.parametrize("ns", ["", "demo/../prod", "Demo Namespace", "d" * 33])
def test_a_malformed_namespace_is_rejected_before_anything_is_opened(ns):
    with pytest.raises(SystemExit, match="not of the form"):
        load(ns, "OW_BILLING_SOURCE_DSN", "MONGODB_ATLAS_URI", "ow_tp_demo",
             "ow_tp_demo_quarantine", conventions_path=CONVENTIONS)


def test_a_connection_string_for_another_cluster_is_refused(monkeypatch):
    monkeypatch.setenv("MONGODB_ATLAS_URI", "mongodb+srv://u:p@someone-else.abcde.mongodb.net/")
    with pytest.raises(SystemExit, match="other than the designated"):
        load("demo", "OW_BILLING_SOURCE_DSN", "MONGODB_ATLAS_URI", "ow_tp_demo",
             "ow_tp_demo_quarantine", conventions_path=CONVENTIONS)
