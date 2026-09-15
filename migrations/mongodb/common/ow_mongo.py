"""Shared helpers for the OW_BILLING -> MongoDB Atlas migration.

Connection details come from environment variables named in the wave brief
(ORACLE_BILLING_URI, MONGODB_ATLAS_URI); no literal credential ever appears here.

The source is read-only: every statement this module issues is a SELECT.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from decimal import Decimal
from typing import Any, Iterable, Iterator

from bson.decimal128 import Decimal128

ORACLE_DSN_SECRET = "ORACLE_BILLING_URI"
MONGO_URI_SECRET = "MONGODB_ATLAS_URI"
TARGET_DB = "ow_billing_migration"

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
_DDMONYY = re.compile(r"^\s*(\d{1,2})-([A-Za-z]{3})-(\d{2})"
                      r"(?:\s+(\d{1,2}):(\d{2}):(\d{2}))?\s*$")


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set in the environment")
    return value


def oracle_connect():
    """Read-only Oracle connection. DSN secret format: user/password/host:port/service."""
    import oracledb
    user, password, dsn = _secret(ORACLE_DSN_SECRET).split("/", 2)
    return oracledb.connect(user=user, password=password, dsn=dsn)


def mongo_db(database: str = TARGET_DB, allowed: Iterable[str] = (TARGET_DB,)):
    """Target database handle, refusing any database outside the allowlist."""
    from pymongo import MongoClient
    if database not in set(allowed):
        raise RuntimeError(f"{database} is not an allowed write target")
    return MongoClient(_secret(MONGO_URI_SECRET))[database]


def rows(conn, sql: str, params: dict | None = None) -> Iterator[dict[str, Any]]:
    """Run one SELECT and yield dict rows. Refuses anything that is not a read."""
    if not re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE):
        raise RuntimeError("source access is read-only: only SELECT/WITH is allowed")
    cur = conn.cursor()
    cur.arraysize = 1000
    cur.execute(sql, params or {})
    names = [d[0] for d in cur.description]
    for row in cur:
        yield dict(zip(names, row))


def load_codes(conn) -> dict[tuple[str, int], str]:
    """The CODES lookup, as PKG_OW_UTIL.f_code_desc reads it."""
    return {(r["CODE_TYPE"], int(r["CODE_VAL"])): r["CODE_DESC"]
            for r in rows(conn, "SELECT code_type, code_val, code_desc FROM codes")}


def decode(codes: dict[tuple[str, int], str], code_type: str, value: Any) -> Any:
    """Decode through CODES; unknown values become UNKNOWN(<n>), as the source does."""
    if value is None:
        return None
    n = int(value)
    hit = codes.get((code_type, n))
    return hit if hit is not None else f"UNKNOWN({n})"


def yn(value: Any) -> bool | None:
    """Y/N to boolean. Anything else is null, and the caller keeps the raw value."""
    if value is None:
        return None
    v = str(value).strip().upper()
    return True if v == "Y" else False if v == "N" else None


def parse_dt(value: Any) -> _dt.datetime | None:
    """Parse the estate's DD-MON-YY[ HH24:MI:SS] strings; unparseable input is null.

    Mirrors PKG_OW_UTIL.f_str2dt, which is TO_DATE(str, 'DD-MON-YY'): the YY format keeps
    the current century, so '31-DEC-99' is 2099, not 1999 (RR's 1950/2049 window is a
    different format mask and is not what the source uses).
    """
    if value is None or isinstance(value, _dt.datetime):
        return value
    m = _DDMONYY.match(str(value))
    if not m:
        return None
    day, mon, yy, hh, mi, ss = m.groups()
    month = _MONTHS.get(mon.upper())
    if month is None:
        return None
    year = (_dt.datetime.now(_dt.timezone.utc).year // 100) * 100 + int(yy)
    try:
        return _dt.datetime(year, month, int(day),
                            int(hh or 0), int(mi or 0), int(ss or 0),
                            tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


def csv_list(value: Any) -> tuple[list[str], bool]:
    """Split a CSV string into a trimmed list. Returns ([], True) when malformed.

    Malformed means what the estate produces: empty items, a trailing or leading
    separator, or a doubled separator.
    """
    if value is None:
        return [], False
    text = str(value)
    if not text.strip():
        return [], False
    parts = [p.strip() for p in text.split(",")]
    if any(p == "" for p in parts):
        return [], True
    return parts, False


def money(value: Any) -> Decimal128 | None:
    if value is None:
        return None
    return Decimal128(Decimal(str(value)))


def utc(value: Any) -> _dt.datetime | None:
    """Oracle DATE/TIMESTAMP to a UTC datetime truncated to milliseconds."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    value = value.astimezone(_dt.timezone.utc)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def set_raw(doc: dict, path: str, value: Any) -> None:
    """Keep an unconvertible source value under legacy.<field>Raw."""
    section, _, key = path.partition(".")
    doc.setdefault(section, {})[key] = value
