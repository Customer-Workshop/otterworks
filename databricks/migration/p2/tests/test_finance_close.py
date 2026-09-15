"""Fixture-first checks for the finance close.

Run: python3 databricks/migration/p2/tests/test_finance_close.py

The first test is the one that matters: aggregate every captured legacy `.psv` and
compare the rendered report byte for byte with the `.csv` the Perl actually wrote.
The rest pin individual contract clauses so a failure names the clause.

`baseline/captured/reports/` came from running `finance_excel_report.pl`. It is the
source side of recon and is never regenerated from this code.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "databricks/migration/p2/pipeline"))

from custbill_close import close_rows, record_type_name, render_csv

CAPTURED = ROOT / "databricks/migration/p2/baseline/captured"
ENCODING = "iso-8859-1"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


def captured_psv_lines() -> list[str]:
    lines: list[str] = []
    for path in sorted((CAPTURED / "parsed").glob("CUSTBILL*.psv")):
        text = path.read_bytes().decode(ENCODING)
        lines += text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    return lines


def test_report_matches_the_captured_legacy_csv() -> None:
    """The whole point: same input, same report bytes (C-7.1 - C-7.6)."""
    expected = (CAPTURED / "reports/finance_billing_20260915.csv").read_bytes().decode(ENCODING)
    actual = render_csv(close_rows(captured_psv_lines()))
    check("report is byte-identical to the legacy csv", actual == expected, _first_diff(expected, actual))


def test_xls_is_the_same_bytes_as_the_csv() -> None:
    """`cp $csv $xls`. The extension is a lie about the format and stays one (C-7.7)."""
    csv = (CAPTURED / "reports/finance_billing_20260915.csv").read_bytes()
    xls = (CAPTURED / "reports/finance_billing_20260915.xls").read_bytes()
    check("captured .xls is a byte copy of the .csv", csv == xls, f"{len(csv)} vs {len(xls)} bytes")


def test_delimiter_collision_groups_on_the_shifted_fields() -> None:
    """A `|` in the name shifts the split, so the report groups on the wrong bytes (C-5.1, C-7.2)."""
    rows = close_rows(captured_psv_lines())
    keys = {(row["currency"], row["record_type"]) for row in rows}
    check("shifted record keeps its shifted group", ("0US", "UNKNOWN(D0)") in keys, repr(sorted(keys)))


def test_record_type_names() -> None:
    """01 and 02 are named; everything else is reported raw inside UNKNOWN() (C-7.3)."""
    named = [record_type_name(rt) for rt in ("01", "02", "03", "", "1 ")]
    check(
        "record type naming",
        named == ["INVOICE", "CREDIT", "UNKNOWN(03)", "UNKNOWN()", "UNKNOWN(1 )"],
        repr(named),
    )


def test_empty_customer_id_is_skipped() -> None:
    """`next if ($cust eq "")`, which is what makes a blank input line contribute nothing (C-7.4)."""
    rows = close_rows(["|||0.00||", "C1|n|2026-01-01|10.00|USD|01", ""])
    check("only the row with a customer id counts", len(rows) == 1 and rows[0]["record_count"] == 1, repr(rows))


def test_non_numeric_amount_counts_as_zero_not_as_a_skip() -> None:
    """Perl's `+=` coerces; the row still counts, it just adds nothing (C-3.3, C-7.1)."""
    rows = close_rows(["C1|n|2026-01-01|junk|USD|01", "C2|n|2026-01-01|5.50|USD|01"])
    check(
        "junk amount adds zero and keeps its row in the count",
        rows == [{"currency": "USD", "rec_type": "01", "record_type": "INVOICE", "record_count": 2, "total_amount": 5.5}],
        repr(rows),
    )


def test_keys_sort_as_strings() -> None:
    """`sort keys %tot` over `"$ccy|$rt"`: digits, then upper case, then lower case (C-7.5)."""
    rows = close_rows(
        [
            "a|n|d|1.00|usd|01",
            "b|n|d|1.00|USD|01",
            "c|n|d|1.00|USD|02",
            "d|n|d|1.00|0US|01",
            "e|n|d|1.00||",
        ]
    )
    order = [f"{row['currency']}|{row['rec_type']}" for row in rows]
    check("key order", order == ["0US|01", "USD|01", "USD|02", "usd|01", "|"], repr(order))


def test_short_line_pads_missing_fields() -> None:
    """A line with fewer than six fields gives undef, not an error (C-3.6, C-7.4)."""
    rows = close_rows(["C1|n|2026-01-01"])
    check(
        "missing currency and type group as empty strings",
        rows == [{"currency": "", "rec_type": "", "record_type": "UNKNOWN()", "record_count": 1, "total_amount": 0.0}],
        repr(rows),
    )


def _first_diff(expected: str, actual: str) -> str:
    for index, (left, right) in enumerate(zip(expected.split("\n"), actual.split("\n"))):
        if left != right:
            return f"line {index + 1}: expected {left!r}, got {right!r}"
    return f"{len(expected.splitlines())} vs {len(actual.splitlines())} lines"


for test in [value for name, value in sorted(globals().items()) if name.startswith("test_")]:
    test()

if failures:
    print(f"\n{len(failures)} check(s) failed")
    sys.exit(1)
print("\nall finance close checks passed")
