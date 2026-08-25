from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "db" / "documents.json"

COLLECTIONS = (
    "customers",
    "plans",
    "subscriptions",
    "usage_events",
    "rating_periods",
    "invoices",
    "credit_notes",
)

FIELD_TYPES: dict[str, dict[str, str]] = {
    "plans": {"monthly_fee": "money", "overage_rate": "money"},
    "subscriptions": {
        "starts_on": "date",
        "ends_on": "date",
        "suspended_on": "date",
    },
    "usage_events": {"occurred_at": "timestamp"},
    "rating_periods": {
        "period_start": "date",
        "period_end": "date",
        "result.overage_amount": "money",
        "result.created_at": "timestamp",
    },
    "invoices": {
        "issued_at": "timestamp",
        "subtotal": "money",
        "tax": "money",
        "total": "money",
        "lines.amount": "money",
    },
    "credit_notes": {
        "issued_on": "date",
        "amount": "money",
        "remaining_amount": "money",
    },
}

INDEXES = {
    "subscriptions": "tenant_id",
    "usage_events": "tenant_id",
    "credit_notes": "tenant_id",
    "rating_periods": "tenant_id",
    "invoices": "tenant_id",
}

_client: MongoClient | None = None


def client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            settings.document_uri,
            uuidRepresentation="standard",
            tz_aware=True,
            tzinfo=UTC,
        )
    return _client


def database() -> Database:
    return client()[settings.document_db]


def _convert(value: Any, field_type: str) -> Any:
    if value is None:
        return None
    if field_type == "money":
        return Decimal128(Decimal(value))
    if field_type == "date":
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
    if field_type == "timestamp":
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    raise ValueError(f"unknown document field type: {field_type}")


def convert_document(collection: str, document: dict[str, Any]) -> dict[str, Any]:
    converted = dict(document)
    for path, field_type in FIELD_TYPES.get(collection, {}).items():
        parts = path.split(".")
        if parts[0] == "lines":
            converted["lines"] = [
                {**line, "amount": _convert(line["amount"], field_type)}
                for line in converted["lines"]
            ]
        elif len(parts) == 2:
            nested = converted.get(parts[0])
            if nested is not None:
                converted[parts[0]] = {
                    **nested,
                    parts[1]: _convert(nested[parts[1]], field_type),
                }
        else:
            converted[parts[0]] = _convert(converted.get(parts[0]), field_type)
    return converted


def load_seed() -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(SEED.read_text())
    return {
        collection: [convert_document(collection, document) for document in documents]
        for collection, documents in raw.items()
    }


def reset_documents() -> None:
    target = database()
    seed = load_seed()
    for collection in COLLECTIONS:
        target.drop_collection(collection)
        documents = seed[collection]
        if documents:
            target[collection].insert_many(documents, ordered=True)
    for collection, field in INDEXES.items():
        target[collection].create_index([(field, ASCENDING)])
