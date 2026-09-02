"""Unit tests for the pure helpers of the `finance` notebook (U8 finance_excel_report).

The notebook is imported as a module; its `main()` (Spark/dbutils) is guarded by
`__name__ == "__main__"` and never runs here.
"""
from __future__ import annotations

import importlib.util
import io
import itertools
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

NOTEBOOK = Path(__file__).resolve().parents[3] / "infrastructure/terraform-databricks/notebooks/finance.py"


def _load():
    spec = importlib.util.spec_from_file_location("finance_notebook", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


finance = _load()

LEGACY_ROWS = [
    ("EUR", "INVOICE", 21, Decimal("108695.69")),
    ("EUR", "CREDIT", 7, Decimal("35335.42")),
    ("GBP", "INVOICE", 23, Decimal("99792.87")),
    ("GBP", "CREDIT", 10, Decimal("51512.05")),
    ("USD", "INVOICE", 33, Decimal("139649.08")),
    ("USD", "CREDIT", 6, Decimal("26123.77")),
]
LEGACY_CSV = (
    b"Currency,RecordType,RecordCount,TotalAmount\n"
    b"EUR,INVOICE,21,108695.69\n"
    b"EUR,CREDIT,7,35335.42\n"
    b"GBP,INVOICE,23,99792.87\n"
    b"GBP,CREDIT,10,51512.05\n"
    b"USD,INVOICE,33,139649.08\n"
    b"USD,CREDIT,6,26123.77\n"
)


@pytest.mark.parametrize("rt,name", [
    ("01", "INVOICE"),
    ("02", "CREDIT"),
    ("03", "UNKNOWN(03)"),
    ("", "UNKNOWN()"),
    ("1", "UNKNOWN(1)"),
    ("XX", "UNKNOWN(XX)"),
])
def test_record_type_name_matches_perl_ternary(rt: str, name: str) -> None:
    assert finance.record_type_name(rt) == name


def test_order_rows_matches_perl_sort_on_ccy_pipe_rt_key() -> None:
    keys = [(c, rt) for c in ("USD", "EUR", "GBP", "AAA", "ZZZ", "A0B")
            for rt in ("02", "01", "03", "9", "XX", "")]
    perl_order = sorted(keys, key=lambda k: finance.legacy_sort_key(*k))
    assert finance.order_rows(keys) == perl_order


def test_order_rows_is_deterministic_for_every_permutation_of_legacy_keys() -> None:
    keys = [(r[0], "01" if r[1] == "INVOICE" else "02") for r in LEGACY_ROWS]
    for perm in itertools.islice(itertools.permutations(keys), 200):
        assert finance.order_rows(list(perm)) == keys


def test_aggregate_uses_exact_decimal_and_skips_empty_cust_id() -> None:
    records = [
        ("C1", Decimal("0.10"), "USD", "01"),
        ("C2", Decimal("0.20"), "USD", "01"),
        ("", Decimal("999.99"), "USD", "01"),
        ("C3", "0.30", "EUR", "02"),
        ("C4", Decimal("1.05"), "EUR", "07"),
    ]
    assert finance.aggregate(records) == [
        ("EUR", "02", 1, Decimal("0.30")),
        ("EUR", "07", 1, Decimal("1.05")),
        ("USD", "01", 2, Decimal("0.30")),
    ]
    assert all(isinstance(r[3], Decimal) for r in finance.aggregate(records))


def test_aggregate_rejects_float_and_nulls() -> None:
    with pytest.raises(TypeError):
        finance.aggregate([("C1", 0.1, "USD", "01")])
    for bad in [("C1", None, "USD", "01"), ("C1", Decimal(1), None, "01"), ("C1", Decimal(1), "USD", None)]:
        with pytest.raises(ValueError):
            finance.aggregate([bad])


def test_aggregate_of_hundred_cents_is_exact() -> None:
    records = [(f"C{i}", Decimal("0.01"), "USD", "01") for i in range(100)]
    assert finance.aggregate(records) == [("USD", "01", 100, Decimal("1.00"))]


def test_report_rows_maps_types_and_quantizes() -> None:
    assert finance.report_rows([("EUR", "01", 2, Decimal(3)), ("EUR", "05", 1, Decimal("1.5"))]) == [
        ("EUR", "INVOICE", 2, Decimal("3.00")),
        ("EUR", "UNKNOWN(05)", 1, Decimal("1.50")),
    ]


def test_render_csv_is_byte_identical_to_legacy_layout() -> None:
    data = finance.render_csv(LEGACY_ROWS)
    assert data == LEGACY_CSV
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


def test_render_csv_header_only_when_no_rows() -> None:
    assert finance.render_csv([]) == b"Currency,RecordType,RecordCount,TotalAmount\n"


def test_format_amount_is_two_decimals_without_float() -> None:
    assert finance.format_amount(Decimal(0)) == "0.00"
    assert finance.format_amount(Decimal("139649.08")) == "139649.08"
    assert finance.format_amount(Decimal("1E+3")) == "1000.00"
    with pytest.raises(TypeError):
        finance.format_amount(1.5)


@pytest.mark.parametrize("value,expected", [
    ("2026-09-01", date(2026, 9, 1)),
    (" 2024-02-29 ", date(2024, 2, 29)),
    ("", date(2030, 1, 2)),
    (None, date(2030, 1, 2)),
])
def test_resolve_report_date_defaults_to_today(value, expected) -> None:
    assert finance.resolve_report_date(value, today=date(2030, 1, 2)) == expected


def test_resolve_report_date_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        finance.resolve_report_date("20260901")


def test_stamp_and_export_paths_follow_legacy_filename() -> None:
    assert finance.report_stamp(date(2026, 9, 1)) == "20260901"
    csv_path, xlsx_path = finance.export_paths("finance-w2", date(2026, 9, 1))
    assert csv_path == "/Volumes/ow_tp/bronze/landing/finance-w2/reports/finance_billing_20260901.csv"
    assert xlsx_path == "/Volumes/ow_tp/bronze/landing/finance-w2/reports/finance_billing_20260901.xlsx"


def test_render_xlsx_cells_match_csv_values() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(io.BytesIO(finance.render_xlsx(LEGACY_ROWS)), data_only=True)
    assert wb.sheetnames == ["finance_billing"]
    ws = wb["finance_billing"]
    cells = [list(r) for r in ws.iter_rows(values_only=True)]
    assert cells[0] == ["Currency", "RecordType", "RecordCount", "TotalAmount"]
    assert [[r[0], r[1], int(r[2]), f"{Decimal(str(r[3])):.2f}"] for r in cells[1:]] == [
        [r[0], r[1], r[2], f"{r[3]:.2f}"] for r in LEGACY_ROWS
    ]
    assert all(isinstance(r[3], float) for r in cells[1:])
    assert ws.cell(row=2, column=4).number_format == "0.00"


def test_render_xlsx_header_only_when_no_rows() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    ws = openpyxl.load_workbook(io.BytesIO(finance.render_xlsx([])))["finance_billing"]
    assert [list(r) for r in ws.iter_rows(values_only=True)] == [["Currency", "RecordType", "RecordCount", "TotalAmount"]]


@pytest.mark.parametrize("ns", ["demo", "finance-w2", "a" * 32])
def test_require_ns_accepts(ns: str) -> None:
    assert finance.require_ns(ns) == ns


@pytest.mark.parametrize("ns", ["", "Demo", "-x", "a" * 33, "x;drop", "ns'--"])
def test_require_ns_rejects(ns: str) -> None:
    with pytest.raises(ValueError):
        finance.require_ns(ns)
