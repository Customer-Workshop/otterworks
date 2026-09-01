"""Unit tests for the pure helpers of the `parse` notebook."""
from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[3] / "infrastructure/terraform-databricks/notebooks/parse.py"


def _load():
    spec = importlib.util.spec_from_file_location("parse_notebook", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


parse = _load()


def body_line(
    cust_id: str = "CUST000001",
    cust_name: str = "Acme",
    bill_date: str = "20240229",
    bill_amt: str = "000000123456",
    currency: str = "USD",
    rec_type: str = "01",
) -> str:
    return (
        cust_id.ljust(10)
        + cust_name.ljust(30)
        + bill_date
        + bill_amt
        + currency.ljust(3)
        + rec_type
    )


def test_slice_fields_uses_fixed_offsets_and_ignores_extra_bytes() -> None:
    line = body_line(cust_id="ID12345678", cust_name="A" * 30, currency="EUR", rec_type="1 ") + "extra"
    assert len(line) == 70
    assert parse.slice_fields(line) == {
        "cust_id": "ID12345678",
        "cust_name": "A" * 30,
        "bill_date": "20240229",
        "bill_amt": "000000123456",
        "currency": "EUR",
        "rec_type": "1 ",
    }


def test_rtrim_spaces_only_strips_trailing_spaces() -> None:
    assert parse.rtrim_spaces("  A  B   ") == "  A  B"
    assert parse.rtrim_spaces("leading\t") == "leading\t"
    assert parse.rtrim_spaces("value \t") == "value \t"


def test_parse_amount_is_exact_decimal_with_two_places() -> None:
    amount = parse.parse_amount("000000123456")
    assert amount == Decimal("1234.56")
    assert amount.as_tuple().exponent == -2
    assert parse.parse_amount("000000000000") == Decimal("0.00")
    assert parse.parse_amount("00000ABC1234") is None
    assert parse.parse_amount("00000000000") is None


def test_parse_bill_date_requires_a_real_calendar_date() -> None:
    assert parse.parse_bill_date("20230231") is None
    assert parse.parse_bill_date("20240229") == date(2024, 2, 29)
    assert parse.parse_bill_date("20230229") is None
    assert parse.parse_bill_date("2023ab01") is None
    assert parse.parse_bill_date("20230715") == date(2023, 7, 15)


def test_short_record_is_quarantined_without_slicing() -> None:
    short = "x" * 64
    assert parse.parse_body_line("file.dat", 4, short) == (None, ["short_record"])
    parsed, reasons = parse.parse_body_line("file.dat", 5, body_line())
    assert parsed is not None
    assert reasons == []


def test_parse_trailer_count_strips_leading_zeroes() -> None:
    assert parse.parse_trailer_count("TRL0000000050") == 50
    assert parse.parse_trailer_count("TRL0000000000") == 0
    assert parse.parse_trailer_count("TRL00000000AB") is None


def test_multi_defect_body_row_emits_reasons_in_fixed_order() -> None:
    parsed, reasons = parse.parse_body_line(
        "file.dat",
        9,
        body_line(bill_date="20230231", bill_amt="00000ABC1234"),
    )
    assert parsed is None
    assert reasons == ["nonnumeric_amount", "invalid_calendar_date"]


def test_parse_file_loads_valid_rows_and_quarantines_body_and_trailer_defects() -> None:
    lines = [
        (1, "HDR", "HDRCUSTBILL"),
        (2, "BODY", body_line(cust_id="CUST000001")),
        (3, "BODY", body_line(cust_id="CUST000002", bill_date="20230231")),
        (4, "BODY", body_line(cust_id="CUST000003")),
        (5, "TRL", "TRL0000000003"),
    ]
    silver, quarantine = parse.parse_file("CUSTBILL_A.dat", lines)
    assert len(silver) == 2
    assert len(quarantine) == 1
    assert quarantine == [("CUSTBILL_A.dat", 3, lines[2][2], "invalid_calendar_date")]

    mismatch_lines = lines[:-1] + [(5, "TRL", "TRL0000000004")]
    silver, quarantine = parse.parse_file("CUSTBILL_A.dat", mismatch_lines)
    assert len(silver) == 2
    assert quarantine[-1] == (
        "CUSTBILL_A.dat",
        5,
        "TRL0000000004",
        "trailer_count_mismatch",
    )


def test_header_and_zero_trailer_without_body_is_empty() -> None:
    assert parse.parse_file(
        "CUSTBILL_EMPTY.dat",
        [(1, "HDR", "HDRCUSTBILL"), (2, "TRL", "TRL0000000000")],
    ) == ([], [])


def test_empty_fields_are_empty_strings_and_rec_type_is_untrimmed() -> None:
    parsed, reasons = parse.parse_body_line(
        "file.dat",
        1,
        body_line(cust_name=" " * 30, rec_type="1 "),
    )
    assert reasons == []
    assert parsed is not None
    assert parsed.cust_name == ""
    assert parsed.cust_name is not None
    assert parsed.rec_type == "1 "


def test_require_ns_validates_lowercase_namespace() -> None:
    assert parse.require_ns("parse-w2-anom") == "parse-w2-anom"
    for ns in ("Demo", "", "a" * 33, "x_y"):
        try:
            parse.require_ns(ns)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {ns!r}")
