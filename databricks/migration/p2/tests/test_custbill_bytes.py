"""Fixture-first checks for the bronze record split, against the captured legacy bytes.

Run: python3 databricks/migration/p2/tests/test_custbill_bytes.py

The captured baseline under databricks/migration/p2/baseline/captured/ is the
legacy chain's own output over the pinned fixtures. If the split here disagrees
with it, bronze is already wrong and no amount of downstream parity will show it.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "databricks/migration/p2/pipeline"))

from custbill_bytes import (
    byte_offsets,
    data_records,
    is_header_or_trailer,
    split_records,
)

CAPTURED = ROOT / "databricks/migration/p2/baseline/captured"
ENCODING = "iso-8859-1"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


def test_round_trip_is_lossless() -> None:
    """Every byte survives decode. This is the claim C-1.4 rests on."""
    for path in sorted((CAPTURED / "inputs").glob("*.dat")):
        raw = path.read_bytes()
        rebuilt = "\n".join(r[1] for r in split_records(raw)).encode(ENCODING)
        if raw.endswith(b"\n"):
            rebuilt += b"\n"
        check(f"round-trip {path.name}", rebuilt == raw, f"{len(rebuilt)} bytes vs {len(raw)}")


def test_record_count_matches_the_legacy_psv() -> None:
    """Records that survive HDR/TRL deletion == lines the legacy parser emitted."""
    for psv in sorted((CAPTURED / "parsed").glob("*.psv")):
        dat = CAPTURED / "inputs" / (psv.stem + ".dat")
        if not dat.exists():
            continue
        body = psv.read_bytes()
        # An empty input yields a zero-byte psv, which is zero records, not one
        # empty one (contract: empty in, empty out).
        expected = len(body.rstrip(b"\n").split(b"\n")) if body else 0
        got = len(data_records(dat.read_bytes()))
        check(f"record count {dat.name}", got == expected, f"bronze {got} vs legacy psv {expected}")


def test_byte_offsets_locate_the_record() -> None:
    """The offset quarantine reports must find the record in the file (C-6.1)."""
    for path in sorted((CAPTURED / "inputs").glob("*.dat")):
        raw = path.read_bytes()
        records = split_records(raw)
        wrong = [
            (rec[0], offset)
            for rec, offset in zip(records, byte_offsets(records))
            if raw[offset : offset + rec[2]] != rec[1].encode(ENCODING)
        ]
        check(f"offsets locate every record in {path.name}", not wrong, repr(wrong[:3]))


def test_byte_offsets_survive_uneven_records() -> None:
    """Short, blank, long and CR-carrying lines all shift what follows them."""
    content = b"short\n\n" + b"x" * 80 + b"\nwith-cr\r\n"
    offsets = byte_offsets(split_records(content))
    check("offsets follow record length", offsets == [0, 6, 7, 88], repr(offsets))


def test_blank_line_is_a_record() -> None:
    got = split_records(b"A\n\nB\n")
    check("blank line kept", len(got) == 3 and got[1][1] == "", repr(got))


def test_no_trailing_newline() -> None:
    got = split_records(b"A\nB")
    check("last record without LF kept", len(got) == 2 and got[1][1] == "B", repr(got))


def test_cr_stays_inside_the_record() -> None:
    got = split_records(b"A\r\n")
    check("CR preserved", got == [(1, "A\r", 2)], repr(got))


def test_hdr_shadowing() -> None:
    """A customer id starting with HDR is deleted, exactly as the legacy does (C-4.1)."""
    check("HDR prefix deleted", is_header_or_trailer("HDRCUST001  ACME"), "")
    check("TRL prefix deleted", is_header_or_trailer("TRL000014"), "")
    check("ordinary record kept", not is_header_or_trailer("C000000001NORMAL"), "")


def test_high_bytes_survive() -> None:
    got = split_records(b"\xe9\xc3\xa9\n")
    check("latin-1 and utf-8 bytes both survive", got[0][2] == 3 and got[0][1].encode(ENCODING) == b"\xe9\xc3\xa9", repr(got))


if __name__ == "__main__":
    test_round_trip_is_lossless()
    test_record_count_matches_the_legacy_psv()
    test_byte_offsets_locate_the_record()
    test_byte_offsets_survive_uneven_records()
    test_blank_line_is_a_record()
    test_no_trailing_newline()
    test_cr_stays_inside_the_record()
    test_hdr_shadowing()
    test_high_bytes_survive()
    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        sys.exit(1)
    print("all bronze byte checks passed")
