"""Collection shape for the migrated file metadata: validator + indexes.

Applied to `ow_tp_mongodb_<ns>.files` only. Nothing here touches a collection
outside this workload.
"""

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid

from files_common import COLLECTION, QUARANTINE_COLLECTION

VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "otterworks file metadata",
        "required": ["tenant", "storage_key", "modified_at"],
        "properties": {
            "_id": {"bsonType": "string"},
            "legacy_id": {"bsonType": "string"},
            "tenant": {"bsonType": "string"},
            "storage_key": {"bsonType": "string"},
            "modified_at": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "name": {"bsonType": "string"},
            "mime_type": {"bsonType": "string"},
            "size_bytes": {"bsonType": ["int", "long"]},
            "version": {"bsonType": ["int", "long"]},
            "is_trashed": {"bsonType": "bool"},
            "folder_id": {"bsonType": "string"},
            "owner_id": {"bsonType": "string"},
            "orphaned_metadata": {"bsonType": "bool"},
            "extras": {"bsonType": "object"},
        },
    }
}

INDEXES = [
    ({"keys": [("tenant", ASCENDING)], "name": "tenant"}),
    ({"keys": [("tenant", ASCENDING), ("storage_key", ASCENDING)],
      "name": "tenant_storage_key", "unique": True}),
    ({"keys": [("tenant", ASCENDING), ("legacy_id", ASCENDING)],
      "name": "tenant_legacy_id", "unique": True}),
    ({"keys": [("tenant", ASCENDING), ("orphaned_metadata", ASCENDING)],
      "name": "tenant_orphaned_metadata"}),
    ({"keys": [("tenant", ASCENDING), ("modified_at", DESCENDING)],
      "name": "tenant_modified_at"}),
    ({"keys": [("tenant", ASCENDING), ("owner_id", ASCENDING)],
      "name": "tenant_owner"}),
]

QUARANTINE_INDEXES = [
    ({"keys": [("reason", ASCENDING)], "name": "reason"}),
    ({"keys": [("source_key", ASCENDING)], "name": "source_key"}),
]


def ensure_collection(db, name: str) -> None:
    """Create `name` with the validator, or bring an existing one up to it."""
    try:
        db.create_collection(
            name, validator=VALIDATOR, validationLevel="strict",
            validationAction="error",
        )
    except CollectionInvalid:
        db.command({
            "collMod": name, "validator": VALIDATOR,
            "validationLevel": "strict", "validationAction": "error",
        })


def ensure_indexes(collection, specs) -> list[str]:
    return [
        collection.create_index(
            spec["keys"], name=spec["name"], unique=spec.get("unique", False)
        )
        for spec in specs
    ]


def setup(files_db, quarantine_db) -> dict:
    """Idempotently apply the collection shape for this workload."""
    ensure_collection(files_db, COLLECTION)
    if QUARANTINE_COLLECTION not in quarantine_db.list_collection_names():
        quarantine_db.create_collection(QUARANTINE_COLLECTION)
    return {
        "files_indexes": ensure_indexes(files_db[COLLECTION], INDEXES),
        "quarantine_indexes": ensure_indexes(
            quarantine_db[QUARANTINE_COLLECTION], QUARANTINE_INDEXES),
    }
