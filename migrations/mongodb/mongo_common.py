"""Shared helpers for the MongoDB document-estate migration.

Naming, deterministic id derivation, and the baseline checksum algorithm used by
the legacy estate's manifest live here so the migration and its reconciliation
agree by construction.

The checksum is order-independent by design: each line's md5 digest is summed
modulo 2**128, so a value recomputed from the document store can be compared to
the estate baseline without depending on read order.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone

# Namespaces for uuid5 derivation. Fixed strings: the migrated key of a source
# row must be reproducible from the row alone, on any machine, forever.
_ROOT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://otterworks.internal/tp/mongodb")
DOCUMENT_ID_NS = uuid.uuid5(_ROOT_NS, "documents")
SNAPSHOT_ID_NS = uuid.uuid5(_ROOT_NS, "document_snapshots")

DB_PREFIX = "ow_tp_mongodb"
DOCUMENTS = "documents"
SNAPSHOTS = "document_snapshots"
QUARANTINE = "documents_quarantine"

# A document's version history is embedded, so it must stay bounded. A source
# document with more versions than this is quarantined rather than truncated.
MAX_EMBEDDED_VERSIONS = 200


def _validate_ns(ns: str) -> str:
    if not isinstance(ns, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,30}", ns) is None:
        raise SystemExit(
            f"invalid namespace {ns!r}: must match ^[a-z][a-z0-9_]{{0,30}}$"
        )
    return ns


def database_name(ns: str) -> str:
    return f"{DB_PREFIX}_{_validate_ns(ns)}"


def quarantine_database_name(ns: str) -> str:
    return f"{DB_PREFIX}_{_validate_ns(ns)}_quarantine"


def source_schema(ns: str) -> str:
    return f"otterworks_{_validate_ns(ns)}"


def document_key(ns: str, legacy_id: str) -> str:
    """Deterministic migrated key for a source documents row."""
    return str(uuid.uuid5(DOCUMENT_ID_NS, f"{ns}:{legacy_id}"))


def snapshot_key(ns: str, legacy_id: str) -> str:
    """Deterministic migrated key for a source document_snapshots row."""
    return str(uuid.uuid5(SNAPSHOT_ID_NS, f"{ns}:{legacy_id}"))


class Checksum:
    """Order-independent checksum matching the estate baseline manifest."""

    _MOD = 1 << 128

    def __init__(self) -> None:
        self._total = 0
        self.count = 0

    def add(self, line: str) -> None:
        digest = hashlib.md5(line.encode()).digest()
        self._total = (self._total + int.from_bytes(digest, "big")) % self._MOD
        self.count += 1

    def hexdigest(self) -> str:
        return f"{self._total:032x}"


def pg_config() -> dict:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "otterworks"),
        "user": os.getenv("DB_USER", "otterworks"),
        "password": os.getenv("DB_PASSWORD", "otterworks_dev"),
    }


def mongo_uri(run_mode: str) -> str:
    """Connection string for the requested run mode.

    ``fixture`` never falls back to the shared cluster: a fixture run that
    silently reached a shared deployment would invalidate its own evidence.
    """
    if run_mode == "fixture":
        uri = os.getenv("TP_MONGO_FIXTURE_URI", "mongodb://localhost:27117")
        if "mongodb.net" in uri:
            raise SystemExit("refusing to run a fixture migration against a shared cluster")
        return uri
    uri = os.getenv("MONGODB_ATLAS_URI")
    if not uri:
        raise SystemExit("MONGODB_ATLAS_URI is not set; live run refused")
    return uri


def utc(value: datetime) -> datetime:
    """Normalise a timestamp to a tz-aware UTC datetime for BSON date storage."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
