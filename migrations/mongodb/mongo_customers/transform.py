"""Pure row -> document transforms for the customers migration.

Everything in this module is deterministic and side-effect free: the same
CUSTOMER_MASTER row always produces the same document and the same quarantine
attributions, which is what makes a rerun byte-identical.

Policy encoded here (from the unit contract):

* `_id` is `uuid5(ID_NAMESPACE, "<namespace>:<CUST_ID>")` — never `uuid4`.
* Text is carried through byte-for-byte after decoding: no trimming, case
  folding or Unicode normalisation. A value that cannot be represented as
  UTF-8 is quarantined as `invalid_encoding` with its raw bytes as hex; it is
  never replaced with U+FFFD and never dropped.
* `SIGNUP_DT` accepts strict `DD-MON-YY` only. Anything else (`31-FEB-24`,
  `N/A`, `29-FEB-23`, ...) is quarantined as `dirty_date` and the field is
  omitted — never coerced, defaulted, or written as null.
* CSV list columns become real arrays. A malformed list is tolerated: the
  parsable elements are kept and the row is attributed in the quarantine
  ledger with the raw source string.
* Sparse columns are emitted only when the source value is non-null.
* A missing required source value (CUST_ID) quarantines the row rather than
  letting a NULL fail open into a valid-looking document.
"""

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from bson import Decimal128

from schema import (BALANCE_COLUMNS, LEGACY_COLUMNS, LIST_COLUMNS, SOURCE_TABLE)

# Fixed namespace for uuid5 derivation. Changing it re-keys every document, so
# it is a constant of the migration contract.
ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL,
                          "https://otterworks.example/tp/mongodb/customers")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}

LEGACY_DATE_RE = re.compile(r"^(\d{2})-([A-Z]{3})-(\d{2})$")
# A well-formed list element: no surrounding whitespace, no empty elements, no
# embedded separators or literals like NULL/NONE.
LIST_ELEMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")
LIST_LITERALS = {"NULL", "NONE", "N/A"}


class Attribution:
    """One quarantine ledger entry for a source row."""

    __slots__ = ("reason", "field", "raw_value", "raw_hex", "parsed_elements", "detail")

    def __init__(self, reason, field=None, raw_value=None, raw_hex=None,
                 parsed_elements=None, detail=None):
        self.reason = reason
        self.field = field
        self.raw_value = raw_value
        self.raw_hex = raw_hex
        self.parsed_elements = parsed_elements
        self.detail = detail

    def document(self, namespace: str, customer_id: str, batch_no: int) -> dict:
        doc = {
            "_id": quarantine_id(namespace, customer_id, self.reason, self.field),
            "customer_id": customer_id,
            "namespace": namespace,
            "reason": self.reason,
            "source": {"table": SOURCE_TABLE, "batch_no": batch_no},
        }
        for key in ("field", "raw_value", "raw_hex", "parsed_elements", "detail"):
            value = getattr(self, key)
            if value is not None:
                doc[key] = value
        return doc

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Attribution({self.reason!r}, field={self.field!r})"


def document_id(namespace: str, customer_id: str) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{namespace}:{customer_id}")


def quarantine_id(namespace: str, customer_id: str, reason: str, field) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE,
                      f"{namespace}:{customer_id}:{reason}:{field or ''}")


def decode_text(value):
    """Return (text, raw_hex). raw_hex is set when the value is not valid UTF-8."""
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8"), None
        except UnicodeDecodeError:
            return None, bytes(value).hex()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        # Lone surrogates survive a lossy decode upstream; keep the bytes.
        return None, value.encode("utf-8", "surrogatepass").hex()
    return value, None


def parse_legacy_date(raw):
    """Strict DD-MON-YY -> aware UTC datetime. Returns (value, error_reason)."""
    if raw is None:
        return None, None
    match = LEGACY_DATE_RE.match(raw)
    if not match:
        return None, "dirty_date"
    day, mon, year = match.group(1), match.group(2), int(match.group(3))
    if mon not in MONTHS:
        return None, "dirty_date"
    # Legacy two-digit years follow the estate's RR convention: 00-49 -> 2000s.
    century = 2000 if year <= 49 else 1900
    try:
        value = datetime(century + year, MONTHS[mon], int(day), tzinfo=timezone.utc)
    except ValueError:
        return None, "dirty_date"
    return value, None


def parse_csv_list(raw):
    """Comma-separated VARCHAR2 -> (elements, malformed).

    A well-formed list is either empty (-> `[]`) or a comma-separated run of
    non-empty tokens. A malformed list yields only its parsable elements and is
    flagged so the caller can attribute the row.
    """
    if raw is None:
        return None, False
    if raw == "":
        return [], False
    parts = raw.split(",")
    elements, malformed = [], False
    for part in parts:
        if LIST_ELEMENT_RE.match(part) and part.upper() not in LIST_LITERALS:
            elements.append(part)
        else:
            malformed = True
    return elements, malformed


def _money(value):
    if isinstance(value, Decimal128):
        return value
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return Decimal128(value.quantize(Decimal("0.01")))


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _legacy_value(column: str, value, attributions: list):
    kind = LEGACY_COLUMNS[column]
    if kind == "string":
        text, raw_hex = decode_text(value)
        if text is None:
            attributions.append(Attribution("invalid_encoding", field=column.upper(),
                                            raw_hex=raw_hex))
            return None
        return text
    if kind == "long":
        return int(value)
    if kind == "decimal":
        return _money(value)
    return _as_utc(value)


def build_document(row: dict, namespace: str, batch_no: int):
    """Map one CUSTOMER_MASTER row. Returns (document | None, attributions)."""
    attributions = []

    raw_customer_id = row.get("cust_id")
    if raw_customer_id is None or raw_customer_id == "":
        attributions.append(Attribution("missing_required_field", field="CUST_ID",
                                        detail="CUST_ID is null or empty; the row "
                                               "cannot be keyed and is not migrated"))
        return None, attributions
    customer_id, raw_hex = decode_text(raw_customer_id)
    if customer_id is None:
        attributions.append(Attribution("invalid_encoding", field="CUST_ID",
                                        raw_hex=raw_hex))
        return None, attributions

    doc = {
        "_id": document_id(namespace, customer_id),
        "customer_id": customer_id,
        "namespace": namespace,
        "source": {"table": SOURCE_TABLE, "batch_no": int(batch_no)},
    }

    for column, target in (("cust_no", "customer_no"), ("cust_name", "customer_name"),
                           ("legal_name", "legal_name"), ("tenant_id", "tenant_id")):
        value = row.get(column)
        if value is None:
            continue
        text, raw_hex = decode_text(value)
        if text is None:
            attributions.append(Attribution("invalid_encoding", field=column.upper(),
                                            raw_hex=raw_hex))
            continue
        doc[target] = text

    signup_raw = row.get("signup_dt")
    if signup_raw is not None:
        text, raw_hex = decode_text(signup_raw)
        if text is None:
            attributions.append(Attribution("invalid_encoding", field="SIGNUP_DT",
                                            raw_hex=raw_hex))
        else:
            value, error = parse_legacy_date(text)
            if error:
                attributions.append(Attribution(error, field="SIGNUP_DT", raw_value=text,
                                                detail="not a valid DD-MON-YY calendar "
                                                       "date; left unset rather than coerced"))
            else:
                doc["signup_dt"] = value

    for column, target in LIST_COLUMNS.items():
        raw = row.get(column)
        if raw is None:
            continue
        text, raw_hex = decode_text(raw)
        if text is None:
            attributions.append(Attribution("invalid_encoding", field=column.upper(),
                                            raw_hex=raw_hex))
            continue
        elements, malformed = parse_csv_list(text)
        doc[target] = elements
        if malformed:
            attributions.append(Attribution("malformed_csv_list", field=column.upper(),
                                            raw_value=text, parsed_elements=elements))

    balances = {}
    for column, target in BALANCE_COLUMNS.items():
        value = row.get(column)
        if value is not None:
            balances[target] = _money(value)
    if balances:
        doc["balances"] = balances

    legacy = {}
    for column in LEGACY_COLUMNS:
        value = row.get(column)
        if value is None:
            continue
        mapped = _legacy_value(column, value, attributions)
        if mapped is not None:
            legacy[column] = mapped
    if legacy:
        doc["legacy"] = legacy

    return doc, attributions


def build_attribute_entry(attr_value, attr_type, created_dt):
    """One folded ENTITY_ATTR_VALUE row. Returns (entry, error_reason).

    `CREATED_DT` is a `DD-MON-YY` string in the source like every other legacy
    date. A parsable value becomes a BSON date; an unparsable one is preserved
    verbatim as `created_dt_raw` rather than being coerced or dropped. It is an
    audit annotation, not a required target field, so it does not quarantine
    the attribute.
    """
    if attr_value is None:
        return None, "null_attribute_value"
    text, raw_hex = decode_text(attr_value)
    if text is None:
        return {"raw_hex": raw_hex}, "invalid_encoding"
    entry = {"value": text}
    if attr_type is not None:
        type_text, raw_hex = decode_text(attr_type)
        if type_text is None:
            return {"raw_hex": raw_hex}, "invalid_encoding"
        entry["attr_type"] = type_text
    if created_dt is not None:
        raw_text, raw_hex = decode_text(created_dt)
        if raw_text is None:
            return {"raw_hex": raw_hex}, "invalid_encoding"
        value, error = parse_legacy_date(raw_text)
        if error:
            entry["created_dt_raw"] = raw_text
        else:
            entry["created_dt"] = value
    return entry, None
