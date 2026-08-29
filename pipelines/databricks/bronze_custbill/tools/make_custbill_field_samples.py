#!/usr/bin/env python3
"""Write CUSTBILL drop files containing the record shapes the production feed
actually carries, byte-exact per copybook CBCUST01.

The mainframe extract (job CB77340 on MVSPROD) is not clean: `BILL-AMT` arrives
non-numeric when the originating COBOL program hits an uninitialised working
storage field, `BILL-DATE` carries impossible values because nothing validates
it upstream, some records are truncated mid-transfer, some carry trailing
operator annotations past byte 65, and occasional records contain a non-ASCII
byte that shifts every `cut -c` column downstream. Trailer counts have
disagreed with the detail-record count since ETL-0187 (2011) was closed unfixed.

Emitting those shapes into the drop directory is what lets the conversion prove
its anomaly handling against the legacy parser's own output instead of asserting
it in prose. Output is deterministic: no clock, no randomness.

Usage:
  python3 make_custbill_field_samples.py <drop_dir>
"""

from __future__ import annotations

import pathlib
import sys

CUST_ID_LEN, CUST_NAME_LEN = 10, 30
BILL_DATE_LEN, BILL_AMT_LEN = 8, 12
CURRENCY_LEN, REC_TYPE_LEN = 3, 2
RECORD_LEN = 65


def detail(cust_id: str, name: str, date: str, amt: str, ccy: str, rec_type: str) -> bytes:
    """Lay one detail record out at the copybook's byte positions."""
    for value, width in (
        (cust_id, CUST_ID_LEN),
        (name, CUST_NAME_LEN),
        (date, BILL_DATE_LEN),
        (amt, BILL_AMT_LEN),
        (ccy, CURRENCY_LEN),
        (rec_type, REC_TYPE_LEN),
    ):
        if len(value) > width:
            raise ValueError(f"{value!r} exceeds its {width}-byte copybook field")
    record = (
        cust_id.ljust(CUST_ID_LEN)
        + name.ljust(CUST_NAME_LEN)
        + date.ljust(BILL_DATE_LEN)
        + amt.rjust(BILL_AMT_LEN, "0")
        + ccy.ljust(CURRENCY_LEN)
        + rec_type.ljust(REC_TYPE_LEN)
    )
    assert len(record) == RECORD_LEN, len(record)
    return record.encode("ascii")


def header(file_seq: str) -> bytes:
    return f"HDR CUSTBILL EXTRACT NS=DEMO       FILE={file_seq}".encode("ascii")


def trailer(count: int) -> bytes:
    return f"TRL{str(count).zfill(10)}".encode("ascii")


def field_shapes_file() -> bytes:
    """Detail records covering every malformed shape the feed produces."""
    records = [
        # impossible calendar date (2024-02-31); source reformats it blindly
        detail("C000900001", "ACME HOLDINGS", "20240231", "000000123456", "USD", "01"),
        # non-numeric BILL-AMT; awk's `amt=$4+0` coerces this to 0 in the source
        detail("C000900002", "NORTHWIND TRADING", "20250115", "00000ABC1234", "USD", "01"),
        # truncated mid-transfer: 26 bytes, the source `cut` pads it into empty fields
        b"C000900003SHORT RECORD CO",
        # operator annotation appended past byte 65
        detail("C000900004", "UMBRELLA CORP", "20250216", "000000998877", "USD", "02")
        + b"/RESEND01",
        # non-ASCII byte (0xC9) inside CUST-NAME shifts every downstream column
        b"C000900005"
        + (b"CAF" + b"\xc9" + b" GLOBAL").ljust(CUST_NAME_LEN, b" ")
        + b"20250317"
        + b"000000054321"
        + b"USD"
        + b"01",
        # zero-filled BILL-DATE
        detail("C000900006", "STARK INDUSTRIES", "00000000", "000000777000", "USD", "01"),
        # all-space CUST-NAME and CURRENCY
        detail("C000900007", "", "20250401", "000000045000", "", "01"),
        # implied decimal at the top of the field's range
        detail("C000900008", "VEHEMENT CAPITAL", "20250402", "000099999999", "USD", "02"),
        detail("C000900009", "SOYLENT CORP", "20250403", "000000010000", "USD", "01"),
        detail("C000900010", "MASSIVE DYNAMIC", "20250404", "000000250050", "USD", "02"),
        detail("C000900011", "WERNHAM HOGG", "20250405", "000001234567", "USD", "01"),
        detail("C000900012", "DUNDER MIFFLIN", "20250406", "000000000001", "USD", "01"),
    ]
    lines = [header("003"), *records, trailer(len(records))]
    return b"\n".join(lines) + b"\n"


def trailer_mismatch_file() -> bytes:
    """TRL count disagrees with the detail-record count (ETL-0187)."""
    records = [
        detail("C000910001", "CYBERDYNE SYSTEMS", "20250501", "000000320000", "USD", "01"),
        detail("C000910002", "TYRELL CORP", "20250502", "000000410000", "USD", "01"),
        detail("C000910003", "OSCORP", "20250503", "000000150000", "USD", "02"),
    ]
    lines = [header("004"), *records, trailer(5)]
    return b"\n".join(lines) + b"\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    drop = pathlib.Path(sys.argv[1])
    drop.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("CUSTBILL_DEMO_003.dat", field_shapes_file()),
        ("CUSTBILL_DEMO_004.dat", trailer_mismatch_file()),
    ):
        path = drop / name
        path.write_bytes(payload)
        print(f"wrote {path} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
