"""Shared helpers for the mongo_invoices workload.

Source: Oracle OW_BILLING.INVOICE_HEADER + OW_BILLING.INVOICE_LINE.
Target: MongoDB collection ow_tp_mongodb_<ns>.invoices, with rejected source
rows in ow_tp_mongodb_<ns>_quarantine.invoice_lines_quarantine.

Every identifier is derived, never generated: document ids are uuid5 over a
fixed namespace so a rerun produces the same _id for the same source key.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import oracledb
from bson.decimal128 import Decimal128
from pymongo import MongoClient

# Money and quantities must not pass through binary floating point.
oracledb.defaults.fetch_decimals = True

UNIT = "mongo_invoices"
SOURCE_SYSTEM = "oracle"
SOURCE_SCHEMA = "OW_BILLING"
HEADER_TABLE = "INVOICE_HEADER"
LINE_TABLE = "INVOICE_LINE"

COLLECTION = "invoices"
QUARANTINE_COLLECTION = "invoice_lines_quarantine"

# Fixed uuid5 namespace: ids are reproducible across runs, machines and
# namespaces. Never uuid4.
ID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://otterworks.internal/tp/mongodb/mongo_invoices"
)

# The bounded document model the target collection is designed around. Invoices
# above it are migrated and reported, never silently truncated or split.
BOUNDED_LINES_PER_INVOICE = 25

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

QUARANTINE_REASONS = (
    "orphan_no_header",
    "header_unusable",
    "null_amount",
    "null_quantity",
    "null_foreign_key",
    "invalid_encoding",
    "extra_delimited_fields",
    "invalid_date",
)


def ns_seed(ns: str) -> int:
    return int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)


def batch_no(ns: str) -> int:
    """The estate tags every row of a namespace with this conversion batch."""
    return ns_seed(ns) % 90_000_000 + 1_000_000


def db_name(ns: str) -> str:
    return f"ow_tp_mongodb_{ns}"


def quarantine_db_name(ns: str) -> str:
    return f"ow_tp_mongodb_{ns}_quarantine"


def invoice_doc_id(ns: str, invoice_id: str) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{ns}:invoice:{invoice_id}")


def quarantine_doc_id(ns: str, line_id: str, reason: str) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{ns}:quarantine:{reason}:{line_id}")


def oracle_connect():
    return oracledb.connect(
        user=os.environ.get("DB_USER", "ow_billing"),
        password=os.environ.get("DB_PASSWORD", "ow_billing"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "52521")),
        service_name=os.environ.get("DB_SERVICE", "FREEPDB1"),
    )


def mongo_uri() -> str:
    """Target URI. Defaults to the local fixture, never to a shared cluster."""
    return os.environ.get("TP_MONGODB_URI", "mongodb://localhost:27017")


def mongo_client() -> MongoClient:
    return MongoClient(
        mongo_uri(),
        uuidRepresentation="standard",
        tz_aware=True,
        tzinfo=timezone.utc,
        serverSelectionTimeoutMS=int(os.environ.get("TP_MONGODB_TIMEOUT_MS", "20000")),
    )


def run_mode() -> str:
    """`fixture` for a local document-store fixture, `live` for Atlas."""
    uri = mongo_uri()
    return "fixture" if ("localhost" in uri or "127.0.0.1" in uri) else "live"


def parse_legacy_date(value):
    """Parse a legacy DD-MON-YY field into an aware UTC datetime.

    Returns None for a NULL field and raises ValueError for text that is not a
    date; callers quarantine rather than substitute a placeholder.
    """
    if value is None:
        return None
    raw = value.strip()
    parts = raw.split("-")
    if len(parts) != 3:
        raise ValueError(f"not a DD-MON-YY date: {value!r}")
    day_s, mon_s, year_s = parts
    if not (day_s.isdigit() and year_s.isdigit() and len(year_s) == 2):
        raise ValueError(f"not a DD-MON-YY date: {value!r}")
    month = MONTHS.get(mon_s.upper())
    if month is None:
        raise ValueError(f"not a DD-MON-YY date: {value!r}")
    year = int(year_s)
    year += 2000 if year <= 68 else 1900
    try:
        return datetime(year, month, int(day_s), tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"not a calendar date: {value!r}") from exc


def to_decimal128(value) -> Decimal128:
    """Carry an Oracle NUMBER across as BSON decimal, with no float step."""
    if isinstance(value, Decimal):
        return Decimal128(value)
    return Decimal128(Decimal(str(value)))


def money(value: Decimal128) -> Decimal:
    return value.to_decimal()


def money_text(value: Decimal) -> str:
    """The estate's canonical two-decimal money rendering."""
    return f"{value:.2f}"


def undecodable_hex(value: str):
    """Hex of the raw bytes of text the source could not decode as UTF-8.

    oracledb decodes AL32UTF8 with surrogateescape for bytes it cannot map, so
    a lone surrogate is the signal that the stored bytes are not valid UTF-8.
    """
    if not isinstance(value, str):
        return None
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        return None
    return value.encode("utf-8", "surrogateescape").hex()


def parse_gl_accounts(csv_value):
    """Split the GL account CSV into accounts plus unattributed leftovers."""
    if csv_value is None:
        return [], []
    accounts, leftovers = [], []
    for token in csv_value.split(","):
        stripped = token.strip()
        if stripped.isdigit() and stripped == token:
            accounts.append(int(stripped))
        else:
            leftovers.append(token)
    return accounts, leftovers


INVOICE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "ow_tp invoices",
        "required": ["_id", "ns", "source", "invoice_no", "issue_date", "lines"],
        "properties": {
            "_id": {"bsonType": "binData"},
            "ns": {"bsonType": "string"},
            "invoice_no": {"bsonType": "string"},
            "issue_date": {"bsonType": "date"},
            "due_date": {"bsonType": ["date", "null"]},
            "status_code": {"bsonType": ["int", "null"]},
            "header_total": {"bsonType": ["decimal", "null"]},
            "lines_total": {"bsonType": "decimal"},
            "lines_tax_total": {"bsonType": "decimal"},
            "lines_count": {"bsonType": "int"},
            "source": {
                "bsonType": "object",
                "required": ["system", "schema", "table", "invoice_id"],
                "properties": {
                    "system": {"bsonType": "string"},
                    "schema": {"bsonType": "string"},
                    "table": {"bsonType": "string"},
                    "invoice_id": {"bsonType": "string"},
                    "batch_no": {"bsonType": ["int", "null"]},
                },
            },
            "customer": {
                "bsonType": "object",
                "properties": {
                    "cust_id": {"bsonType": ["string", "null"]},
                    "tenant_id": {"bsonType": ["string", "null"]},
                },
            },
            "lines": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["line_id", "amount", "tax_amt"],
                    "properties": {
                        "line_id": {"bsonType": "string"},
                        "line_no": {"bsonType": ["int", "null"]},
                        "line_type_code": {"bsonType": ["int", "null"]},
                        "item_desc": {"bsonType": ["string", "null"]},
                        "qty": {"bsonType": "decimal"},
                        "unit_price": {"bsonType": "decimal"},
                        "amount": {"bsonType": "decimal"},
                        "tax_amt": {"bsonType": "decimal"},
                        "line_date": {"bsonType": ["date", "null"]},
                        "service_period": {"bsonType": ["string", "null"]},
                        "posted": {"bsonType": ["string", "null"]},
                        "gl_accounts": {
                            "bsonType": "array",
                            "items": {"bsonType": "int"},
                        },
                    },
                },
            },
        },
    }
}

QUARANTINE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "ow_tp quarantined invoice lines",
        "required": ["_id", "ns", "reason", "source"],
        "properties": {
            "_id": {"bsonType": "binData"},
            "ns": {"bsonType": "string"},
            "reason": {"enum": list(QUARANTINE_REASONS)},
            "source": {
                "bsonType": "object",
                "required": ["system", "schema", "table", "line_id"],
                "properties": {
                    "system": {"bsonType": "string"},
                    "schema": {"bsonType": "string"},
                    "table": {"bsonType": "string"},
                    "line_id": {"bsonType": "string"},
                    "invoice_id": {"bsonType": ["string", "null"]},
                    "invoice_no": {"bsonType": ["string", "null"]},
                    "cust_id": {"bsonType": ["string", "null"]},
                },
            },
        },
    }
}

INVOICE_INDEXES = [
    {"keys": [("ns", 1), ("source.invoice_id", 1)], "name": "ns_source_invoice_id", "unique": True},
    {"keys": [("ns", 1), ("invoice_no", 1)], "name": "ns_invoice_no"},
    {"keys": [("ns", 1), ("customer.cust_id", 1), ("issue_date", -1)], "name": "ns_cust_issue_date"},
    {"keys": [("ns", 1), ("lines.line_id", 1)], "name": "ns_line_id"},
]

QUARANTINE_INDEXES = [
    {
        "keys": [("ns", 1), ("source.line_id", 1), ("reason", 1)],
        "name": "ns_line_id_reason",
        "unique": True,
    },
    {"keys": [("ns", 1), ("reason", 1)], "name": "ns_reason"},
]


def ensure_collection(db, name: str, validator: dict, indexes: list[dict]) -> None:
    """Create or update the collection contract, never dropping data."""
    if name not in db.list_collection_names():
        db.create_collection(name, validator=validator, validationLevel="strict",
                             validationAction="error")
    else:
        db.command({
            "collMod": name,
            "validator": validator,
            "validationLevel": "strict",
            "validationAction": "error",
        })
    for spec in indexes:
        db[name].create_index(spec["keys"], name=spec["name"],
                              unique=spec.get("unique", False))
