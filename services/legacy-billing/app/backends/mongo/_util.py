"""Helpers shared by the wave-1 unit modules (subscriptions_rating, invoicing, dunning).

Ports pkg_ow_util.f_md5_uuid (deterministic ids) and the Oracle date idioms the PL/SQL
packages lean on (TRUNC, day arithmetic, TO_CHAR(..., 'YYYYMMDD') comparisons).
Money is app-side Decimal, stored as Decimal128 with the column's declared scale.
"""
import hashlib
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from bson.decimal128 import Decimal128
from bson.int64 import Int64

TIER_LABELS = {1: "starter", 2: "growth", 3: "scale"}
SUB_STATUS = {10: "active", 20: "suspended", 30: "cancelled"}
TENANT_STATUS = {10: "active", 20: "suspended"}
USAGE_KIND = {1: "api", 2: "storage", 3: "compute"}

MONEY = Decimal("0.01")


def md5_uuid(text):
    """pkg_ow_util.f_md5_uuid: MD5 of the input, formatted 8-4-4-4-12, lower-case."""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def as_datetime(value):
    """Oracle DATE (midnight) semantics for a date / ISO string / datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return datetime.fromisoformat(str(value))


def trunc(value):
    """Oracle TRUNC(date): midnight of the day."""
    d = as_datetime(value)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def day_ceiling(value):
    """Exclusive upper bound for 'TO_CHAR(x,'YYYYMMDD') <= TO_CHAR(day)' -> x < day + 1."""
    return trunc(value) + timedelta(days=1)


def ymd(value):
    return trunc(value).strftime("%Y-%m-%d")


def plain(value):
    """Decimal128 -> Decimal, Int64 -> int, else unchanged."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Int64):
        return int(value)
    return value


def dec(value):
    if value is None:
        return None
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def oround(value, places=2):
    """Oracle ROUND(n, places): half away from zero; NULL propagates."""
    if value is None:
        return None
    q = Decimal(1).scaleb(-places)
    return dec(value).quantize(q, rounding=ROUND_HALF_UP)


def money(value):
    """Decimal -> Decimal128 at NUMBER(12,2) scale; NULL -> None (stored as missing)."""
    if value is None:
        return None
    return Decimal128(dec(value).quantize(MONEY))


def num_out(value):
    """JSON-friendly rendering that matches the Oracle backend's _json_value (str for decimals)."""
    value = plain(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def strip_none(doc):
    """NULL -> missing (mapping rule null_missing_equiv / empty_string_is_null)."""
    return {k: v for k, v in doc.items() if v is not None}
