"""The fixed-width parse, as `parse_custbill_fixedwidth.sh` actually performs it.

No pyspark import: this is the unit whose mistakes are invisible until recon, so
it has to run against the captured legacy `.psv` output without a cluster.

The legacy is `cut | paste | awk`, and the order of those three matters more than
the copybook does:

    paste -d'|' <(cut -c1-10 …) … <(cut -c64-65 …) | awk -F'|' '…'

`cut` slices bytes, `paste` renders them into one `|`-delimited line, and only
then does `awk` split that line on `|` and transform *positional* fields. When a
slice contains a `|` byte the line gains a field and every transform lands on the
wrong data: the date transform runs on the tail of the name, the amount transform
on the date, and the surplus field is printed as-is (contract C-5.1). Parsing the
six slices independently and then joining them would quietly repair that, so the
rendered line is built first and the transforms are applied to it positionally,
exactly as awk does.

Clauses implemented here: C-3.1 (trailing spaces stripped from positional fields
1, 2 and 5 only), C-3.2, C-3.3 (`strtod`-prefix amount), C-3.4 (negatives),
C-3.5 (substr date, never validated), C-3.6 (empty string, never NULL), C-5.1.
"""

from __future__ import annotations

import re

ENCODING = "iso-8859-1"

# 1-based inclusive byte ranges from copybook CBCUST01, as byte slices.
FIELD_SLICES = (
    ("cust_id", 0, 10),
    ("cust_name", 10, 40),
    ("bill_date", 40, 48),
    ("bill_amt", 48, 60),
    ("currency", 60, 63),
    ("rec_type", 63, 65),
)
RECORD_BYTES = 65

# awk's `$x + 0`: optional blanks, optional sign, a decimal mantissa, an optional
# exponent, and nothing else is consumed. No hex (POSIX awk does not read 0x1A as
# 26), no inf/nan. What does not match at all is zero.
_NUMERIC_PREFIX = re.compile(r"^[ \t]*[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")


def slice_fields(raw_record: str) -> list[str]:
    """The six `cut -c` slices. Short records give empty tails, long records lose the surplus."""
    data = raw_record.encode(ENCODING)
    return [data[start:end].decode(ENCODING) for _name, start, end in FIELD_SLICES]


def awk_numeric(text: str) -> float:
    """`text + 0` in awk: the leading numeric prefix, or 0 when there is not one."""
    match = _NUMERIC_PREFIX.match(text)
    if not match:
        return 0.0
    return float(match.group(0))


def _rstrip_spaces(text: str) -> str:
    """awk `gsub(/ +$/,"")`: trailing *spaces* only, so a trailing tab or CR stays."""
    return re.sub(r" +$", "", text)


def render_psv(raw_record: str) -> str:
    """The parsed line the legacy writes to `parsed/<file>.psv`, byte for byte."""
    fields = "|".join(slice_fields(raw_record)).split("|")

    # awk addresses fields by position, and only the ones it names.
    for index in (0, 1, 4):
        if index < len(fields):
            fields[index] = _rstrip_spaces(fields[index])
    if len(fields) > 3:
        fields[3] = f"{awk_numeric(fields[3]) / 100:.2f}"
    if len(fields) > 2:
        date = fields[2]
        fields[2] = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
    return "|".join(fields)


def parse_record(raw_record: str) -> dict:
    """Both halves of the silver row: the clean slices and the rendered line.

    Gold re-splits `psv_line`, because that is the string the report reads. The
    sliced columns are what a human would have expected the parser to produce;
    keeping both is what makes the delimiter collision visible instead of lost.
    """
    sliced = slice_fields(raw_record)
    psv_line = render_psv(raw_record)
    return {
        "cust_id": _rstrip_spaces(sliced[0]),
        "cust_name": _rstrip_spaces(sliced[1]),
        "bill_date_raw": sliced[2],
        "bill_amt_raw": sliced[3],
        "currency": _rstrip_spaces(sliced[4]),
        "rec_type": sliced[5],
        "bill_date": f"{sliced[2][0:4]}-{sliced[2][4:6]}-{sliced[2][6:8]}",
        "bill_amt": f"{awk_numeric(sliced[3]) / 100:.2f}",
        "psv_line": psv_line,
        "psv_field_count": psv_line.count("|") + 1,
    }
