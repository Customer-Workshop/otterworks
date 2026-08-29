"""Canonical text form of a bronze_core row, expressed once for Oracle and once for Spark.

Row-level parity needs a value comparison that is independent of transport. Both sides render
every column to the *same* text (fixed scale per declared target type, ISO timestamps to the
microsecond, an explicit NULL sentinel so NULL never collides with a zero-length string), join
with US, and hash. Oracle uses STANDARD_HASH(...,'MD5'), Databricks uses md5(); the hex digests
are directly comparable, which is what makes the recon a real row-level check rather than a
count comparison.

Keeping the two renderings in one file is deliberate: a change to one is visibly a change to
the other, so the comparison cannot silently stop comparing anything.
"""

from __future__ import annotations

from collections.abc import Sequence

NULL_SENTINEL = "<null>"
SEP = "|"  # rendered as chr(31) (US) in SQL; only shown here for documentation

INT_MASK = "FM99999999999999999999999999999999999990"
MASKS = {
    "code": INT_MASK,
    "count": INT_MASK,
    "surrogate": INT_MASK,
    "money": "FM99999999999999990.00",
    "rate": "FM99999999999999990.000000",
}
ORACLE_DATE_FMT = "YYYY-MM-DD HH24:MI:SS"
ORACLE_TS_FMT = "YYYY-MM-DD HH24:MI:SS.FF6"
SPARK_DATE_FMT = "yyyy-MM-dd HH:mm:ss"
SPARK_TS_FMT = "yyyy-MM-dd HH:mm:ss.SSSSSS"


def oracle_text(column: str, cls: str) -> str:
    """Oracle expression rendering a source column as its canonical text, NULL preserved."""
    if cls in ("text", "flag"):
        return f'"{column.upper()}"'
    if cls == "date":
        return f"TO_CHAR(\"{column.upper()}\", '{ORACLE_DATE_FMT}')"
    if cls == "ts":
        return f"TO_CHAR(\"{column.upper()}\", '{ORACLE_TS_FMT}')"
    if cls in MASKS:
        return f"TO_CHAR(\"{column.upper()}\", '{MASKS[cls]}')"
    raise ValueError(f"unknown column class {cls!r}")


def oracle_canon(column: str, cls: str) -> str:
    return f"NVL({oracle_text(column, cls)}, '{NULL_SENTINEL}')"


def oracle_row_hash(columns: Sequence[dict]) -> str:
    """STANDARD_HASH takes VARCHAR2, so this is only used for the parity tables, whose whole
    canonical row fits well inside the 4000-byte SQL string limit."""
    parts = " || CHR(31) || ".join(oracle_canon(c["name"], c["class"]) for c in columns)
    return f"LOWER(STANDARD_HASH({parts}, 'MD5'))"


def spark_canon(column: str, cls: str) -> str:
    """Databricks expression rendering a *typed target* column as the same canonical text."""
    col = f"`{column}`"
    if cls in ("text", "flag"):
        expr = col
    elif cls == "date":
        expr = f"date_format({col}, '{SPARK_DATE_FMT}')"
    elif cls == "ts":
        expr = f"date_format({col}, '{SPARK_TS_FMT}')"
    elif cls in ("code", "count", "surrogate"):
        expr = f"cast(cast({col} AS DECIMAL(38,0)) AS STRING)"
    elif cls == "money":
        expr = f"cast(cast({col} AS DECIMAL(14,2)) AS STRING)"
    elif cls == "rate":
        expr = f"cast(cast({col} AS DECIMAL(12,6)) AS STRING)"
    else:
        raise ValueError(f"unknown column class {cls!r}")
    return f"coalesce({expr}, '{NULL_SENTINEL}')"


def spark_row_hash(columns: Sequence[dict]) -> str:
    parts = ", char(31), ".join(spark_canon(c["name"], c["class"]) for c in columns)
    return f"md5(concat({parts}))"


def hash_fold_oracle(hash_expr: str) -> str:
    """Order-independent digest of a table: sum of the leading 15 hex digits of each row hash."""
    return f"TO_NUMBER(SUBSTR({hash_expr}, 1, 15), 'XXXXXXXXXXXXXXX')"


def hash_fold_spark(hash_expr: str) -> str:
    return f"cast(conv(substr({hash_expr}, 1, 15), 16, 10) AS DECIMAL(38,0))"
