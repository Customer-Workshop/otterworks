"""MongoDB port of the legacy PKG_OW_UTIL package.

The PL/SQL callers of ``log_msg`` (pkg_rating, pkg_invoicing, and pkg_dunning)
belong to units U3-U6 and are not wired here. This module intentionally does
not invent a caller or provide a bootstrap substitute.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from pymongo import WriteConcern
from pymongo.errors import PyMongoError

NS_VALUE = "mongo_032752"
AUDIT_COLLECTION = "billing_audit_log"
AUDIT_TTL_SECONDS = 90 * 24 * 60 * 60
AUDIT_TTL_INDEX_NAME = "ttl_logged_at_90d"
MODULE_MAX_LEN = 30
MESSAGE_MAX_LEN = 4000
RAW_MAX_BYTES = 2000

_LOGGER = logging.getLogger(__name__)
_MONTHS = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)
_MONTH_ABBREVIATIONS = tuple(month[:3] for month in _MONTHS)


def md5_uuid(value):
    """Return the legacy lowercase, hyphenated MD5 UUID representation."""
    text = "" if value is None else str(value)
    raw = text.encode("utf-8")
    if len(raw) > RAW_MAX_BYTES:
        raise ValueError(
            "ORA-06502: PL/SQL: value or conversion error: "
            "raw variable length too long"
        )
    digest = hashlib.md5(raw).hexdigest()
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-"
        f"{digest[16:20]}-{digest[20:]}"
    )


def _oracle_number_text(value) -> str:
    value = Decimal("-1") if value is None else Decimal(str(value))
    if value == value.to_integral_value():
        return str(int(value))
    rendered = format(value, "f").rstrip("0").rstrip(".")
    if rendered.startswith("-0."):
        rendered = "-." + rendered[3:]
    elif rendered.startswith("0."):
        rendered = rendered[1:]
    return rendered


def code_desc(db, code_type, code_val):
    """Look up a composed U0 code key, returning the Oracle fallback on a miss."""
    integral = False
    if code_type is not None and code_val is not None:
        try:
            number = Decimal(str(code_val))
            integral = number.is_finite() and number == number.to_integral_value()
        except (InvalidOperation, ValueError):
            integral = False
    if code_type is not None and integral:
        document = db["codes"].find_one(
            {"_id": f"{code_type}#{int(Decimal(str(code_val)))}"}
        )
        if document is not None:
            return document.get("code_desc")
    return f"UNKNOWN({_oracle_number_text(code_val)})"


def dt2str(value):
    """Render a date with the English ``DD-MON-YY`` Oracle format."""
    if value is None:
        return None
    return f"{value.day:02d}-{_MONTH_ABBREVIATIONS[value.month - 1]}-{value.year % 100:02d}"


def str2dt(text):
    """Parse Oracle's lenient English ``DD-MON-YY`` format.

    Three-digit years are accepted according to the documented 1-4 digit
    shape, but that case is unverified against the source transcript.
    Unparseable values return ``None`` as the PL/SQL function does.
    """
    if text is None:
        return None
    try:
        tokens = re.split(r"[^A-Za-z0-9]+", str(text).strip())
        if len(tokens) != 3:
            return None
        day_text, month_text, year_text = tokens
        if not re.fullmatch(r"\d{1,2}", day_text):
            return None
        if not re.fullmatch(r"[A-Za-z]+", month_text):
            return None
        if not re.fullmatch(r"\d{1,4}", year_text):
            return None
        month_upper = month_text.upper()
        if month_upper in _MONTH_ABBREVIATIONS:
            month = _MONTH_ABBREVIATIONS.index(month_upper) + 1
        elif month_upper in _MONTHS:
            month = _MONTHS.index(month_upper) + 1
        else:
            return None
        year = int(year_text)
        if len(year_text) <= 2:
            year += (date.today().year // 100) * 100
        return datetime(year, month, int(day_text))
    except (TypeError, ValueError):
        return None


def ensure_audit_indexes(db):
    """Ensure the 90-day TTL replacement for disabled JOB_PURGE_AUDIT_LOG.

    The index replaces the disabled hardcoded DELETE job. Its retention is the
    same 90 days, while cleanup changes from one 03:30 batch to a continuous
    approximately 60-second background sweep.
    """
    collection = db.get_collection(AUDIT_COLLECTION)
    collection.create_index(
        [("logged_at", 1)],
        expireAfterSeconds=AUDIT_TTL_SECONDS,
        name=AUDIT_TTL_INDEX_NAME,
    )
    return [index["name"] for index in collection.list_indexes()]


class OwUtil:
    """PKG_OW_UTIL state scoped to one instance instead of one Oracle session.

    The source never resets these globals and no caller reads another session's
    copy, so narrowing their scope changes no observable behavior.
    """

    def __init__(self, db, write_concern=None):
        self.db = db
        self.audit_collection = db.get_collection(
            AUDIT_COLLECTION,
            write_concern=write_concern or WriteConcern("majority"),
        )
        self.call_count = 0
        self.last_module = None
        self.last_uuid = None

    def f_md5_uuid(self, value):
        self.call_count += 1
        result = md5_uuid(value)
        self.last_uuid = result
        return result

    def f_code_desc(self, code_type, code_val):
        return code_desc(self.db, code_type, code_val)

    def f_dt2str(self, value):
        return dt2str(value)

    def f_str2dt(self, text):
        return str2dt(text)

    def log_msg(self, module, message) -> bool:
        """Write an autonomous audit event without accepting a ClientSession.

        The collection's independent write concern and the single-document
        atomic insert keep this write independent from any caller transaction,
        which is the MongoDB equivalent of the source autonomous transaction.
        The source drops events when the module exceeds 30 bytes or its
        character-truncated message exceeds 4000 bytes. The port truncates by
        characters and always records the event, so audit coverage is wider
        than the source by design. Argument, encoding, and driver failures are
        logged at DEBUG and swallowed.
        """
        self.last_module = module
        try:
            document = {
                "_id": ObjectId(),
                "logged_at": datetime.now(timezone.utc).replace(microsecond=0),
                "module": None if module is None else module[:MODULE_MAX_LEN],
                "message": None if message is None else message[:MESSAGE_MAX_LEN],
                "ns": NS_VALUE,
            }
            self.audit_collection.insert_one(document)
        except Exception:
            _LOGGER.debug("billing audit log write failed", exc_info=True)
            return False
        return True
