# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg2-binary", "pymongo==4.8.0"]
# ///
"""Migrate the OtterWorks document estate into MongoDB.

Source (Postgres schema ``otterworks_<ns>``):
  - ``documents``          -> collection ``documents``
  - ``document_versions``  -> bounded ``versions`` subarray on its document
  - ``document_snapshots`` -> collection ``document_snapshots``

Target: database ``ow_tp_mongodb_<ns>``, quarantine database
``ow_tp_mongodb_<ns>_quarantine``.

Policies (unit contract ``mongo_documents``):
  - Migrated keys are ``uuid5`` of the source key, so a rerun rewrites the same
    documents instead of duplicating them.
  - Titles and bodies are read as raw source bytes and decoded as UTF-8 without
    rewriting, trimming, or Unicode normalisation. A value that will not decode
    is quarantined with reason ``invalid_encoding`` and its bytes recorded as
    hex; snapshot state is carried as BSON binary rather than lossily decoded.
  - A NULL owner, version number, or timestamp is never defaulted: the record is
    quarantined with a reason code.
  - Source columns the contract does not name are carried into an ``extras``
    subdocument and counted, never dropped.
  - Version sequences are migrated exactly as found; gaps are reported, never
    renumbered or backfilled. Snapshots whose owning document is absent are
    migrated with a null parent reference and reported, never attached to a
    fabricated parent.
  - An empty source set is a no-op: prior documents are left untouched.

Usage:
    uv run migrations/mongodb/migrate_documents.py --ns demo --run-mode fixture \
        [--batch-size 250] [--summary-json out.json]
    uv run migrations/mongodb/migrate_documents.py --self-test
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from mongo_common import (
    DOCUMENTS,
    MAX_EMBEDDED_VERSIONS,
    QUARANTINE,
    SNAPSHOTS,
    database_name,
    document_key,
    mongo_uri,
    pg_config,
    quarantine_database_name,
    snapshot_key,
    source_schema,
    utc,
)

DOCUMENT_COLUMNS = [
    "id", "title", "content", "content_type", "owner_id", "folder_id",
    "is_deleted", "is_template", "word_count", "version", "created_at", "updated_at",
]
VERSION_COLUMNS = [
    "id", "document_id", "version_number", "title", "content", "created_by", "created_at",
]
SNAPSHOT_COLUMNS = [
    "id", "document_id", "state_b64", "label", "created_by", "created_at",
]
BYTE_COLUMNS = {"title", "content"}
# Fields that must never be defaulted when NULL in the source.
DOCUMENT_REQUIRED = ["owner_id", "version", "created_at", "updated_at", "title"]
VERSION_REQUIRED = ["document_id", "version_number", "created_at", "created_by"]
SNAPSHOT_REQUIRED = ["document_id", "created_at", "created_by", "state_b64"]

DOCUMENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "otterworks document",
        "required": ["ns", "legacy_id", "updated_at", "versions"],
        "properties": {
            "ns": {"bsonType": "string", "description": "tenant namespace, required"},
            "legacy_id": {"bsonType": "string"},
            "updated_at": {"bsonType": "date", "description": "must be a date, not a string"},
            "created_at": {"bsonType": "date"},
            "versions": {
                "bsonType": "array",
                "description": "embedded version history, objects only",
                "items": {
                    "bsonType": "object",
                    "required": ["version", "legacy_id"],
                    "properties": {"version": {"bsonType": "int"}},
                },
            },
            "word_count": {"bsonType": "int"},
            "version": {"bsonType": "int"},
        },
    }
}

SNAPSHOT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ns", "legacy_id", "legacy_document_id", "created_at", "orphaned"],
        "properties": {
            "ns": {"bsonType": "string"},
            "legacy_id": {"bsonType": "string"},
            "legacy_document_id": {"bsonType": "string"},
            "document_id": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "date"},
            "orphaned": {"bsonType": "bool"},
        },
    }
}

DOCUMENT_INDEXES = [
    ({"ns": 1, "legacy_id": 1}, {"name": "ns_legacy_id_unique", "unique": True}),
    ({"ns": 1, "owner_id": 1}, {"name": "ns_owner_id"}),
    ({"ns": 1, "updated_at": -1}, {"name": "ns_updated_at_desc"}),
    ({"ns": 1, "version_gaps": 1}, {"name": "ns_version_gaps", "sparse": True}),
]
SNAPSHOT_INDEXES = [
    ({"ns": 1, "legacy_id": 1}, {"name": "ns_legacy_id_unique", "unique": True}),
    ({"ns": 1, "document_id": 1}, {"name": "ns_document_id"}),
    ({"ns": 1, "orphaned": 1}, {"name": "ns_orphaned"}),
]
QUARANTINE_INDEXES = [
    ({"ns": 1, "source_table": 1, "legacy_id": 1}, {"name": "ns_table_legacy_id_unique", "unique": True}),
    ({"ns": 1, "reason": 1}, {"name": "ns_reason"}),
]


def log(msg: str) -> None:
    print(f"[mongo_documents] {msg}", flush=True)


# ── source decoding / policy ─────────────────────────────────────────────────


class Quarantined(Exception):
    """A source value violated a contract policy and must not be defaulted."""

    def __init__(self, reason: str, detail: dict):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def decode_text(column: str, raw) -> str:
    """Decode source bytes as UTF-8 byte-transparently, or quarantine."""
    if raw is None:
        return None
    data = bytes(raw)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Quarantined(
            "invalid_encoding",
            {"column": column, "raw_hex": data.hex(), "error": str(exc)},
        ) from exc


def require(row: dict, fields: list[str], reason: str) -> None:
    missing = [f for f in fields if row.get(f) is None]
    if missing:
        raise Quarantined(reason, {"null_fields": sorted(missing)})


def split_extras(row: dict, known: list[str]) -> dict:
    """Carry source columns the contract does not name into ``extras``."""
    return {k: v for k, v in row.items() if k not in known}


def jsonable(value):
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (dict,)):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def quarantine_record(ns: str, table: str, legacy_id, reason: str, detail: dict, row: dict) -> dict:
    return {
        "_id": f"{table}:{ns}:{legacy_id}:{reason}",
        "ns": ns,
        "source_table": table,
        "legacy_id": str(legacy_id) if legacy_id is not None else None,
        "reason": reason,
        "detail": jsonable(detail),
        "source_row": jsonable(row),
    }


# ── row transforms (pure) ────────────────────────────────────────────────────


def build_version(ns: str, row: dict) -> dict:
    require(row, VERSION_REQUIRED, "null_required_field")
    title = decode_text("title", row.get("title"))
    content = decode_text("content", row.get("content"))
    version = {
        "legacy_id": str(row["id"]),
        "version": int(row["version_number"]),
        "title": title,
        "content": content,
        "created_by": str(row["created_by"]),
        "created_at": utc(row["created_at"]),
    }
    extras = split_extras(row, VERSION_COLUMNS)
    if extras:
        version["extras"] = jsonable(extras)
    return version


def build_document(ns: str, row: dict, version_rows: list[dict]) -> tuple[dict, list[dict]]:
    """Return the migrated document plus any quarantined version rows."""
    require(row, DOCUMENT_REQUIRED, "null_required_field")
    legacy_id = str(row["id"])
    title = decode_text("title", row.get("title"))
    content = decode_text("content", row.get("content"))

    versions: list[dict] = []
    quarantined: list[dict] = []
    for vrow in version_rows:
        try:
            versions.append(build_version(ns, vrow))
        except Quarantined as exc:
            quarantined.append(
                quarantine_record(ns, "document_versions", vrow.get("id"), exc.reason, exc.detail, vrow)
            )
    versions.sort(key=lambda v: v["version"])
    if len(versions) > MAX_EMBEDDED_VERSIONS:
        raise Quarantined(
            "unbounded_version_array",
            {"versions": len(versions), "max_embedded_versions": MAX_EMBEDDED_VERSIONS},
        )

    numbers = [v["version"] for v in versions]
    declared = int(row["version"])
    highest = max(numbers) if numbers else declared
    gaps = sorted(set(range(1, max(highest, declared) + 1)) - set(numbers))

    doc = {
        "_id": document_key(ns, legacy_id),
        "ns": ns,
        "legacy_id": legacy_id,
        "title": title,
        "content": content,
        "content_type": row.get("content_type"),
        "owner_id": str(row["owner_id"]),
        "folder_id": str(row["folder_id"]) if row.get("folder_id") is not None else None,
        "is_deleted": bool(row.get("is_deleted")),
        "is_template": bool(row.get("is_template")),
        "word_count": int(row["word_count"]),
        "version": declared,
        "created_at": utc(row["created_at"]),
        "updated_at": utc(row["updated_at"]),
        "versions": versions,
        "version_count": len(versions),
        "version_gaps": gaps,
        "source": {"store": "postgres", "schema": source_schema(ns), "table": "documents"},
    }
    extras = split_extras(row, DOCUMENT_COLUMNS)
    if extras:
        doc["extras"] = jsonable(extras)
    return doc, quarantined


def build_snapshot(ns: str, row: dict, parent_exists: bool) -> dict:
    require(row, SNAPSHOT_REQUIRED, "null_required_field")
    legacy_id = str(row["id"])
    legacy_document_id = str(row["document_id"])
    state_b64 = row["state_b64"]
    try:
        state = base64.b64decode(state_b64, validate=True)
    except Exception as exc:
        raise Quarantined("invalid_snapshot_state", {"error": str(exc)}) from exc

    snap = {
        "_id": snapshot_key(ns, legacy_id),
        "ns": ns,
        "legacy_id": legacy_id,
        "legacy_document_id": legacy_document_id,
        # The owning document's migrated key, or null when the estate has no
        # such document: an orphan is reported, never given a fabricated parent.
        "document_id": document_key(ns, legacy_document_id) if parent_exists else None,
        "orphaned": not parent_exists,
        "state": state,
        "state_encoding": "base64-decoded-source-bytes",
        "label": row.get("label"),
        "created_by": str(row["created_by"]),
        "created_at": utc(row["created_at"]),
        "source": {"store": "postgres", "schema": source_schema(ns), "table": "document_snapshots"},
    }
    extras = split_extras(row, SNAPSHOT_COLUMNS)
    if extras:
        snap["extras"] = jsonable(extras)
    return snap


# ── target shape ─────────────────────────────────────────────────────────────


def ensure_collection(db, name: str, validator: dict) -> None:
    existing = db.list_collection_names()
    if name in existing:
        db.command({
            "collMod": name,
            "validator": validator,
            "validationLevel": "strict",
            "validationAction": "error",
        })
    else:
        db.create_collection(
            name, validator=validator, validationLevel="strict", validationAction="error"
        )


def ensure_indexes(collection, specs) -> None:
    for keys, opts in specs:
        collection.create_index(list(keys.items()), **opts)


def prepare_target(client, ns: str) -> tuple:
    db = client[database_name(ns)]
    qdb = client[quarantine_database_name(ns)]
    ensure_collection(db, DOCUMENTS, DOCUMENT_VALIDATOR)
    ensure_collection(db, SNAPSHOTS, SNAPSHOT_VALIDATOR)
    ensure_indexes(db[DOCUMENTS], DOCUMENT_INDEXES)
    ensure_indexes(db[SNAPSHOTS], SNAPSHOT_INDEXES)
    ensure_indexes(qdb[QUARANTINE], QUARANTINE_INDEXES)
    return db, qdb


# ── source reads ─────────────────────────────────────────────────────────────


def actual_columns(cur, schema: str, table: str, contract_columns: list[str]) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    )
    present = [r[0] for r in cur.fetchall()]
    missing = [c for c in contract_columns if c not in present]
    if missing:
        raise SystemExit(f"{schema}.{table} is missing contract columns: {missing}")
    return present


def select_list(columns: list[str], alias: str | None = None) -> str:
    """Project source columns, reading text as raw UTF-8 bytes for transparency."""
    prefix = f"{alias}." if alias else ""
    return ", ".join(
        f"convert_to({prefix}{c}, 'UTF8') AS {c}" if c in BYTE_COLUMNS else f"{prefix}{c}"
        for c in columns
    )


def rows_as_dicts(cur, columns: list[str]) -> list[dict]:
    return [dict(zip(columns, row)) for row in cur.fetchall()]


# ── migration ────────────────────────────────────────────────────────────────


def migrate(ns: str, run_mode: str, batch_size: int) -> dict:
    import psycopg2
    from pymongo import MongoClient, ReplaceOne

    schema = source_schema(ns)
    stats = Counter()
    quarantine_reasons: Counter = Counter()
    gap_documents: dict[str, list[int]] = {}
    orphan_snapshots: list[str] = []
    extras_columns: set[str] = set()

    conn = psycopg2.connect(**pg_config())
    client = MongoClient(mongo_uri(run_mode), uuidRepresentation="standard")
    try:
        conn.set_session(readonly=True)
        cur = conn.cursor()
        cur.execute("SET client_encoding TO 'UTF8'")
        doc_cols = actual_columns(cur, schema, "documents", DOCUMENT_COLUMNS)
        ver_cols = actual_columns(cur, schema, "document_versions", VERSION_COLUMNS)
        snap_cols = actual_columns(cur, schema, "document_snapshots", SNAPSHOT_COLUMNS)
        extras_columns |= (set(doc_cols) - set(DOCUMENT_COLUMNS))
        extras_columns |= (set(ver_cols) - set(VERSION_COLUMNS))
        extras_columns |= (set(snap_cols) - set(SNAPSHOT_COLUMNS))

        cur.execute(f"SELECT count(*) FROM {schema}.documents")
        source_documents = cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM {schema}.document_snapshots")
        source_snapshots = cur.fetchone()[0]
        if source_documents == 0 and source_snapshots == 0:
            log("source set is empty: no-op, prior documents and snapshots left untouched")
            return {
                "ns": ns, "run_mode": run_mode, "database": database_name(ns),
                "empty_source_noop": True, "batches": 0,
                "source": {"documents": 0, "document_versions": 0, "document_snapshots": 0},
                "migrated": {"documents": 0, "versions_embedded": 0, "snapshots": 0},
                "quarantined": {}, "version_gap_documents": {}, "orphaned_snapshots": [],
                "extras_columns": [],
            }

        db, qdb = prepare_target(client, ns)
        documents, snapshots, quarantine = db[DOCUMENTS], db[SNAPSHOTS], qdb[QUARANTINE]

        # -- documents + embedded versions, one batch per trigger granularity --
        cur.execute(f"SELECT {select_list(doc_cols)} FROM {schema}.documents ORDER BY id")
        while True:
            batch = rows_as_dicts_fetchmany(cur, doc_cols, batch_size)
            if not batch:
                break
            stats["batches"] += 1
            ids = [row["id"] for row in batch]
            vcur = conn.cursor()
            vcur.execute(
                f"SELECT {select_list(ver_cols)} FROM {schema}.document_versions "
                "WHERE document_id = ANY(%s::uuid[]) ORDER BY document_id, version_number",
                ([str(i) for i in ids],),
            )
            versions_by_doc: dict[str, list[dict]] = {}
            for vrow in rows_as_dicts(vcur, ver_cols):
                versions_by_doc.setdefault(str(vrow["document_id"]), []).append(vrow)
            vcur.close()

            ops: list = []
            quarantine_ops: list[dict] = []
            for row in batch:
                legacy_id = str(row["id"])
                try:
                    doc, bad_versions = build_document(ns, row, versions_by_doc.get(legacy_id, []))
                except Quarantined as exc:
                    quarantine_ops.append(
                        quarantine_record(ns, "documents", row.get("id"), exc.reason, exc.detail, row)
                    )
                    quarantine_reasons[exc.reason] += 1
                    continue
                quarantine_ops.extend(bad_versions)
                for record in bad_versions:
                    quarantine_reasons[record["reason"]] += 1
                if doc["version_gaps"]:
                    gap_documents[legacy_id] = doc["version_gaps"]
                stats["versions_embedded"] += doc["version_count"]
                ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))

            if ops:
                documents.bulk_write(ops, ordered=False)
                stats["documents"] += len(ops)
            if quarantine_ops:
                quarantine.bulk_write(
                    [ReplaceOne({"_id": r["_id"]}, r, upsert=True) for r in quarantine_ops],
                    ordered=False,
                )
            log(
                f"batch {stats['batches']}: documents={len(ops)} "
                f"versions={stats['versions_embedded']} quarantined={len(quarantine_ops)}"
            )

        # -- snapshots (parent resolved against the source estate) --
        scur = conn.cursor()
        scur.execute(
            f"SELECT {select_list(snap_cols, alias='s')}, (d.id IS NOT NULL) AS parent_exists "
            f"FROM {schema}.document_snapshots s "
            f"LEFT JOIN {schema}.documents d ON d.id = s.document_id ORDER BY s.id"
        )
        snap_batch_cols = snap_cols + ["parent_exists"]
        while True:
            batch = rows_as_dicts_fetchmany(scur, snap_batch_cols, batch_size)
            if not batch:
                break
            stats["snapshot_batches"] += 1
            ops, quarantine_ops = [], []
            for row in batch:
                parent_exists = bool(row.pop("parent_exists"))
                try:
                    snap = build_snapshot(ns, row, parent_exists)
                except Quarantined as exc:
                    quarantine_ops.append(
                        quarantine_record(ns, "document_snapshots", row.get("id"), exc.reason, exc.detail, row)
                    )
                    quarantine_reasons[exc.reason] += 1
                    continue
                if snap["orphaned"]:
                    orphan_snapshots.append(snap["legacy_id"])
                ops.append(ReplaceOne({"_id": snap["_id"]}, snap, upsert=True))
            if ops:
                snapshots.bulk_write(ops, ordered=False)
                stats["snapshots"] += len(ops)
            if quarantine_ops:
                quarantine.bulk_write(
                    [ReplaceOne({"_id": r["_id"]}, r, upsert=True) for r in quarantine_ops],
                    ordered=False,
                )
            log(
                f"snapshot batch {stats['snapshot_batches']}: snapshots={len(ops)} "
                f"orphaned={len(orphan_snapshots)} quarantined={len(quarantine_ops)}"
            )
        scur.close()

        cur.execute(f"SELECT count(*) FROM {schema}.document_versions")
        source_versions = cur.fetchone()[0]
    finally:
        conn.close()
        client.close()

    summary = {
        "ns": ns,
        "run_mode": run_mode,
        "database": database_name(ns),
        "quarantine_database": quarantine_database_name(ns),
        "empty_source_noop": False,
        "batches": stats["batches"] + stats["snapshot_batches"],
        "batch_size": batch_size,
        "source": {
            "documents": source_documents,
            "document_versions": source_versions,
            "document_snapshots": source_snapshots,
        },
        "migrated": {
            "documents": stats["documents"],
            "versions_embedded": stats["versions_embedded"],
            "snapshots": stats["snapshots"],
        },
        "quarantined": dict(sorted(quarantine_reasons.items())),
        "version_gap_documents": dict(sorted(gap_documents.items())),
        "orphaned_snapshots": sorted(orphan_snapshots),
        "extras_columns": sorted(extras_columns),
    }
    log(
        f"migrated {summary['migrated']['documents']} documents, "
        f"{summary['migrated']['versions_embedded']} versions, "
        f"{summary['migrated']['snapshots']} snapshots "
        f"({len(gap_documents)} documents with version gaps, "
        f"{len(orphan_snapshots)} orphaned snapshots, "
        f"{sum(quarantine_reasons.values())} quarantined)"
    )
    return summary


def rows_as_dicts_fetchmany(cur, columns: list[str], size: int) -> list[dict]:
    return [dict(zip(columns, row)) for row in cur.fetchmany(size)]


# ── self-test for policy paths the estate does not exercise ──────────────────


def self_test() -> int:
    ns = "selftest"
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": b"Title", "content": b"Body", "content_type": "text/markdown",
        "owner_id": "22222222-2222-2222-2222-222222222222", "folder_id": None,
        "is_deleted": False, "is_template": False, "word_count": 1, "version": 2,
        "created_at": now, "updated_at": now,
    }
    failures: list[str] = []

    def expect_quarantine(label: str, fn, reason: str) -> None:
        try:
            fn()
        except Quarantined as exc:
            if exc.reason != reason:
                failures.append(f"{label}: expected {reason}, got {exc.reason}")
            else:
                print(f"  ok  {label} -> {exc.reason}")
            return
        failures.append(f"{label}: expected quarantine {reason}, record was accepted")

    expect_quarantine(
        "null owner", lambda: build_document(ns, {**base, "owner_id": None}, []), "null_required_field"
    )
    expect_quarantine(
        "null updated_at", lambda: build_document(ns, {**base, "updated_at": None}, []), "null_required_field"
    )
    expect_quarantine(
        "invalid utf-8 title",
        lambda: build_document(ns, {**base, "title": b"\xff\xfe bad"}, []),
        "invalid_encoding",
    )
    expect_quarantine(
        "unbounded version array",
        lambda: build_document(
            ns, base,
            [
                {"id": f"33333333-3333-3333-3333-{i:012d}", "document_id": base["id"],
                 "version_number": i, "title": b"t", "content": b"c",
                 "created_by": base["owner_id"], "created_at": now}
                for i in range(1, MAX_EMBEDDED_VERSIONS + 2)
            ],
        ),
        "unbounded_version_array",
    )
    expect_quarantine(
        "null version number",
        lambda: build_version(ns, {"id": "44444444-4444-4444-4444-444444444444",
                                   "document_id": base["id"], "version_number": None,
                                   "title": b"t", "content": b"c",
                                   "created_by": base["owner_id"], "created_at": now}),
        "null_required_field",
    )
    expect_quarantine(
        "undecodable snapshot state",
        lambda: build_snapshot(ns, {"id": "55555555-5555-5555-5555-555555555555",
                                    "document_id": base["id"], "state_b64": "not base64!!",
                                    "label": "autosave", "created_by": base["owner_id"],
                                    "created_at": now}, True),
        "invalid_snapshot_state",
    )

    # extra delimited fields are attributed, not dropped
    doc, _ = build_document(ns, {**base, "legacy_region": "emea"}, [])
    if doc.get("extras") != {"legacy_region": "emea"}:
        failures.append(f"extras attribution: got {doc.get('extras')!r}")
    else:
        print("  ok  extra source column -> extras.legacy_region")

    # byte transparency: no trimming, no normalisation
    raw = "  Ünicode\u00a0 title \u212b  "
    doc, _ = build_document(ns, {**base, "title": raw.encode()}, [])
    if doc["title"] != raw:
        failures.append("byte transparency: title was rewritten")
    else:
        print("  ok  title carried through byte-for-byte")

    # version gaps are reported, never renumbered
    vrows = [
        {"id": f"66666666-6666-6666-6666-{i:012d}", "document_id": base["id"],
         "version_number": i, "title": b"t", "content": b"c",
         "created_by": base["owner_id"], "created_at": now}
        for i in (1, 3, 4)
    ]
    doc, _ = build_document(ns, {**base, "version": 4}, vrows)
    if doc["version_gaps"] != [2] or [v["version"] for v in doc["versions"]] != [1, 3, 4]:
        failures.append(f"version gaps: {doc['version_gaps']} / {[v['version'] for v in doc['versions']]}")
    else:
        print("  ok  version gap reported as [2], sequence left as 1,3,4")

    # orphaned snapshot keeps a null parent reference
    snap = build_snapshot(ns, {"id": "77777777-7777-7777-7777-777777777777",
                               "document_id": base["id"], "state_b64": "c3RhdGU=",
                               "label": "orphan", "created_by": base["owner_id"],
                               "created_at": now}, False)
    if snap["document_id"] is not None or not snap["orphaned"] or snap["state"] != b"state":
        failures.append("orphan snapshot handling")
    else:
        print("  ok  orphaned snapshot -> document_id null, orphaned true, state as binary")

    # deterministic keys
    if document_key(ns, base["id"]) != document_key(ns, base["id"]):
        failures.append("document_key is not deterministic")

    for f in failures:
        print(f"  FAIL {f}")
    print(f"self-test: {'PASS' if not failures else 'FAIL'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns")
    parser.add_argument("--run-mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--summary-json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.ns:
        parser.error("--ns is required")

    summary = migrate(args.ns, args.run_mode, args.batch_size)
    if args.summary_json:
        with open(args.summary_json, "w") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
            fh.write("\n")
        log(f"summary written: {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
