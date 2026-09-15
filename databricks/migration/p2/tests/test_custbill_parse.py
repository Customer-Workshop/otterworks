"""Fixture-first checks for the fixed-width parse.

Run: python3 databricks/migration/p2/tests/test_custbill_parse.py

The first test is the one that matters: replay every captured legacy `.psv` from
its `.dat` input and compare bytes. The rest pin individual contract clauses so a
failure says which clause broke rather than only which file.

The captured output under baseline/captured/ was produced by running the real
legacy scripts. It is the source side of recon and is never regenerated from this
code.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "databricks/migration/p2/pipeline"))

from custbill_bytes import data_records
from custbill_expectations import (
    FILE_AUDIT_EXPECTATIONS,
    SILVER_EXPECTATIONS,
    failed_expectations_sql,
)
from custbill_parse import (
    awk_numeric,
    parse_record,
    render_psv,
    slice_fields,
)

CAPTURED = ROOT / "databricks/migration/p2/baseline/captured"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


def _record(**overrides: str) -> str:
    """A well-formed 65-byte record, with named fields overridden in place."""
    fields = {
        "cust_id": "C000000001",
        "cust_name": "ACME CORP",
        "bill_date": "20240101",
        "bill_amt": "000000123456",
        "currency": "USD",
        "rec_type": "01",
    }
    fields.update(overrides)
    return (
        f"{fields['cust_id']:<10}"
        f"{fields['cust_name']:<30}"
        f"{fields['bill_date']:<8}"
        f"{fields['bill_amt']:<12}"
        f"{fields['currency']:<3}"
        f"{fields['rec_type']:<2}"
    )


def test_every_captured_psv_is_reproduced_byte_for_byte() -> None:
    """The whole unit in one assertion: same inputs in, same legacy bytes out."""
    for psv in sorted((CAPTURED / "parsed").glob("*.psv")):
        source = CAPTURED / "inputs" / f"{psv.stem}.dat"
        produced = [render_psv(rec) for _no, rec, _len in data_records(source.read_bytes())]
        expected = psv.read_bytes().decode("iso-8859-1").split("\n")
        if expected and expected[-1] == "":
            expected.pop()
        first_diff = next(
            (f"line {i + 1}: {p!r} != {e!r}" for i, (p, e) in enumerate(zip(produced, expected)) if p != e),
            f"{len(produced)} lines produced, {len(expected)} expected",
        )
        check(f"{psv.name} reproduced byte for byte", produced == expected, first_diff)


def test_trailing_spaces_are_stripped_from_three_fields_only() -> None:
    """C-3.1: the awk gsub names $1, $2 and $5. bill_date, bill_amt and rec_type keep theirs."""
    parsed = parse_record(_record(rec_type="1 ", currency="usd", bill_amt="1           "))
    check(
        "rec_type keeps its trailing space, currency does not",
        parsed["rec_type"] == "1 " and parsed["currency"] == "usd",
        repr(parsed),
    )


def test_leading_spaces_survive_everywhere() -> None:
    """C-3.2."""
    parsed = parse_record(_record(cust_name="   PADDED CO"))
    check("leading spaces are never stripped", parsed["cust_name"] == "   PADDED CO", repr(parsed))


def test_amount_is_a_strtod_prefix_parse() -> None:
    """C-3.3/C-3.4: awk coerces the leading numeric prefix and ignores the rest."""
    cases = {
        "000000123456": 123456.0,
        "12AB": 12.0,
        "1e3": 1000.0,
        "+5": 5.0,
        ".5": 0.5,
        "0x1A": 0.0,
        "": 0.0,
        "   7": 7.0,
        "-000000000100": -100.0,
    }
    wrong = {text: awk_numeric(text) for text, want in cases.items() if awk_numeric(text) != want}
    check("awk numeric coercion matches the legacy", not wrong, repr(wrong))


def test_amount_formatting_and_negatives() -> None:
    check(
        "implied decimal divides by 100 and keeps the sign",
        parse_record(_record(bill_amt="-00000010000"))["bill_amt"] == "-100.00",
        repr(parse_record(_record(bill_amt="-00000010000"))),
    )


def test_date_is_string_surgery_not_a_date() -> None:
    """C-3.5: no validity check, and not always ten characters."""
    nonsense = parse_record(_record(bill_date="20259999"))["bill_date"]
    blank = parse_record(_record(bill_date="        "))["bill_date"]
    check(
        "invalid dates pass through unchanged in shape",
        nonsense == "2025-99-99" and blank == "    -  -  ",
        f"{nonsense!r} {blank!r}",
    )


def test_a_pipe_in_a_field_shifts_every_later_transform() -> None:
    """C-5.1, the nastiest clause: the transforms are positional, not by field name."""
    line = render_psv(_record(cust_name="PIPE|NAME CO", bill_date="20240101", bill_amt="000000020000"))
    fields = line.split("|")
    check(
        "the delimiter collision is reproduced, not repaired",
        len(fields) == 7 and fields[3] == "202401.01" and fields[5] == "USD",
        repr(line),
    )


def test_short_and_long_records() -> None:
    """C-1.5: a short record loses its tail, a long one loses its surplus."""
    short = parse_record("C000000009SHORT")
    long_record = parse_record(_record() + "EXTRA BYTES BEYOND 65")
    check(
        "short record yields empty tail fields, long record discards the surplus",
        short["currency"] == "" and short["bill_amt"] == "0.00" and long_record["rec_type"] == "01",
        f"{short!r} {long_record!r}",
    )


def test_no_field_is_ever_null() -> None:
    """C-3.6: missing means empty string, in every field, including a blank line."""
    blank = parse_record("")
    check(
        "a blank line parses to all-empty fields, never NULL",
        all(value is not None for value in blank.values()) and blank["cust_id"] == "",
        repr(blank),
    )


def test_slices_are_bytes_not_characters() -> None:
    """C-1.3: a two-byte character pushes every later field one byte right."""
    utf8_name = "CAF\u00c3\u00a9 CO"  # what UTF-8 'CAFé' looks like read as bytes
    fields = slice_fields(_record(cust_name=utf8_name))
    check(
        "field boundaries are byte offsets",
        len(fields[1].encode("iso-8859-1")) == 30,
        repr(fields),
    )


def test_every_contract_expectation_is_declared_and_warn_only() -> None:
    """Contract §6 lists ten checks; a missing one is a silently unwatched field."""
    contract = {
        "rec_len_65",
        "cust_id_nonempty",
        "bill_date_valid_iso",
        "bill_amt_all_digits",
        "bill_amt_non_negative",
        "currency_known",
        "rec_type_known",
        "no_delimiter_collision",
        "ascii_only",
    }
    # not_hdr_trl_shadowed is per file, not per row: the deletion happens before
    # parsing, so the record it removes never reaches a silver row to check.
    declared = set(SILVER_EXPECTATIONS) | set(FILE_AUDIT_EXPECTATIONS)
    missing = (contract | {"not_hdr_trl_shadowed"}) - declared
    check("every contract expectation is declared", not missing, repr(missing))
    sql = failed_expectations_sql(SILVER_EXPECTATIONS)
    check(
        "the quarantine column reports every declared expectation by name",
        all(name in sql for name in SILVER_EXPECTATIONS),
        sql,
    )


if __name__ == "__main__":
    test_every_captured_psv_is_reproduced_byte_for_byte()
    test_trailing_spaces_are_stripped_from_three_fields_only()
    test_leading_spaces_survive_everywhere()
    test_amount_is_a_strtod_prefix_parse()
    test_amount_formatting_and_negatives()
    test_date_is_string_surgery_not_a_date()
    test_a_pipe_in_a_field_shifts_every_later_transform()
    test_short_and_long_records()
    test_no_field_is_ever_null()
    test_slices_are_bytes_not_characters()
    test_every_contract_expectation_is_declared_and_warn_only()
    print()
    if failures:
        raise SystemExit("\n".join(failures))
    print("all parse checks passed")
