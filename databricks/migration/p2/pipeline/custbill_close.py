"""The finance close, as `finance_excel_report.pl` actually performs it.

No pyspark import, for the same reason as `custbill_parse`: this has to run against
the captured legacy report without a cluster, so the Spark version in `custbill_gold`
can be checked against something other than itself.

What the Perl does, in the order that matters:

    ($cust, $name, $dt, $amt, $ccy, $rt) = split(/\\|/);
    next if ($cust eq "");
    $tot{"$ccy|$rt"} += $amt;

It re-splits the `.psv` line positionally, so a record whose name contained a `|`
contributes its *shifted* fields: a piece of the name becomes the currency and a
piece of the date becomes the record type. That is where `0US,UNKNOWN(D0)` in the
captured report comes from. Aggregating silver's clean `currency` and `rec_type`
columns instead would silently repair it and change the totals, so this re-splits
the rendered line exactly as the report does (contract C-5.1, C-7.2).

Clauses: C-7.1 (group by currency and record type), C-7.2 (positional re-split),
C-7.3 (`01`/`02` named, anything else `UNKNOWN(x)`), C-7.4 (a row with an empty
first field is skipped, including the all-empty row a blank input line produces),
C-7.5 (keys sorted as strings, `"$ccy|$rt"`), C-7.6 (`%d` and `%.2f` output).
"""

from __future__ import annotations

from custbill_parse import awk_numeric

HEADER = "Currency,RecordType,RecordCount,TotalAmount"
REC_TYPE_NAMES = {"01": "INVOICE", "02": "CREDIT"}
_FIELDS = 6


def record_type_name(rec_type: str) -> str:
    """`($rt eq "01") ? "INVOICE" : ($rt eq "02") ? "CREDIT" : "UNKNOWN($rt)"`."""
    return REC_TYPE_NAMES.get(rec_type, f"UNKNOWN({rec_type})")


def _positional(psv_line: str) -> list[str]:
    """Perl's list assignment from `split`: missing fields are undef, which is "" here."""
    fields = psv_line.split("|")
    return (fields + [""] * _FIELDS)[:_FIELDS]


def close_rows(psv_lines) -> list[dict]:
    """The report's rows, in the report's order.

    One group per (currency, record type) *as re-split from the line*, the count of
    contributing rows, and the sum of the amount field coerced the way Perl coerces
    a string in `+=`: leading numeric prefix, otherwise zero.
    """
    totals: dict[tuple[str, str], float] = {}
    counts: dict[tuple[str, str], int] = {}
    for line in psv_lines:
        cust, _name, _date, amount, currency, rec_type = _positional(line)
        if cust == "":
            continue
        key = (currency, rec_type)
        totals[key] = totals.get(key, 0.0) + awk_numeric(amount)
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "currency": currency,
            "rec_type": rec_type,
            "record_type": record_type_name(rec_type),
            "record_count": counts[(currency, rec_type)],
            "total_amount": totals[(currency, rec_type)],
        }
        for currency, rec_type in sorted(totals, key=lambda k: f"{k[0]}|{k[1]}")
    ]


def render_csv(rows) -> str:
    """`print OUT "%s,%s,%d,%.2f\\n"` under the one header line, and no quoting at all.

    The legacy writes the currency straight into the line, so a currency holding a
    comma would corrupt the file. Nothing quotes or escapes it here either: the
    output is a copy of what the report produces, defects included (C-7.6).
    """
    lines = [HEADER]
    lines += [
        f"{row['currency']},{row['record_type']},{row['record_count']:d},{row['total_amount']:.2f}"
        for row in rows
    ]
    return "\n".join(lines) + "\n"
