"""Spark SQL equivalents of the Oracle date helpers the legacy estate parses through.

`f_str2dt` is `TO_DATE(raw,'DD-MON-YY','NLS_DATE_LANGUAGE=ENGLISH')` with every error
swallowed to NULL. Oracle's TO_DATE is far looser than the format string suggests, and the
shapes it accepts are already measured against the live source by
`databricks/migration/lakebase/w0a_date_parity.py` (wave 0, unit p1-pkg-ow-util): an
unpadded day, a four-digit year, any punctuation as separator, a lower-case month name and
surrounding whitespace all parse, while an impossible day, an unknown month name or an ISO
string return NULL. `try_to_timestamp(col,'dd-MMM-yy')` on its own matches only the
canonical shape and turns the rest into NULLs Oracle does not produce, so the string is
taken apart here the same way the converted Lakebase function takes it apart.

Differences from a plain Spark parse, each one a vector in the wave-0 parity set:

  - the day may be one or two digits and the separators may be any non-alphanumeric run;
  - a two-digit year is `2000 + yy` (Oracle's 'YY' means the current century; Spark's own
    `yy` pivot happens to agree today, but the rule is written out rather than inherited);
  - the month name is matched against a fixed English list, because Oracle reads it under
    NLS_DATE_LANGUAGE=ENGLISH and Spark's month names follow the session locale;
  - an impossible day ('31-FEB-24', '32-JAN-24', '29-FEB-23') is NULL, not rolled forward.

`hist_dt` is the trigger's `TO_CHAR(SYSDATE,'DD-MON-YY HH24:MI:SS')`. The source has no
zone and the plan declares UTC (P1-D3), so the timestamp is converted to UTC explicitly:
`date_format` alone renders in whatever session timezone the writer happens to hold.
"""

from __future__ import annotations

# Same shape as the converted billing.f_str2dt regex, applied to upper(trim(value)).
_RE = r"^([0-9]{1,2})[^0-9A-Z]+([A-Z]{3})[A-Z]*[^0-9A-Z]+([0-9]{1,4})$"
_MONTHS = "JANFEBMARAPRMAYJUNJULAUGSEPOCTNOVDEC"

# Oracle renders SYSDATE in the database's own wall clock; UTC is the declared source zone.
HIST_DT = ("upper(date_format(convert_timezone('UTC', current_timestamp()), "
           "'dd-MMM-yy HH:mm:ss'))")


def _part(col: str, group: int) -> str:
    return f"regexp_extract(upper(trim({col})), '{_RE}', {group})"


def parse_date(col: str) -> str:
    """`f_str2dt(col)` as one Spark SQL expression returning TIMESTAMP_NTZ or NULL."""
    day = f"try_cast({_part(col, 1)} AS INT)"
    year = f"try_cast({_part(col, 3)} AS INT)"
    # locate() lands on 1, 4, 7 ... for a real month name; any other offset is a three-letter
    # run that merely appears inside the list ('ANF'), which Oracle does not accept.
    at = f"locate({_part(col, 2)}, '{_MONTHS}')"
    month = (f"CASE WHEN pmod({at}, 3) = 1 THEN cast({at} / 3 AS INT) + 1 END")
    century = (f"CASE WHEN length({_part(col, 3)}) <= 2 THEN 2000 + {year} "
               f"ELSE {year} END")
    iso = f"format_string('%04d-%02d-%02d', {century}, {month}, {day})"
    return f"try_to_timestamp({iso}, 'yyyy-MM-dd')"
