# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo==4.10.1", "boto3"]
# ///
"""Migrate file metadata from the legacy DynamoDB table into MongoDB.

    uv run migrations/mongodb/mongo_files/migrate.py --ns demo
    uv run migrations/mongodb/mongo_files/migrate.py --self-test

Reads `otterworks-file-metadata` for one namespace (fully paginated), maps each
item to a document in `ow_tp_mongodb_<ns>.files`, and routes items whose
required attributes are missing or unreadable to
`ow_tp_mongodb_<ns>_quarantine.files_quarantine` with a reason code.

Writes are per-batch upserts keyed on the deterministic document id, so a rerun
converges on the same documents instead of duplicating them. An empty
namespace-filtered scan is a no-op: prior documents are left untouched.

Target selection is explicit: the local fixture unless MONGO_FILES_TARGET=live.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pymongo import MongoClient, ReplaceOne  # noqa: E402

import collection_setup  # noqa: E402
from files_common import (  # noqa: E402
    COLLECTION,
    QUARANTINE_COLLECTION,
    db_names,
    mongo_uri,
    run_mode,
    scan_pages,
    transform,
)

BATCH_SIZE = 500


def log(msg: str) -> None:
    print(f"[mongo-files] {msg}", flush=True)


def _flush(collection, ops: list) -> int:
    if not ops:
        return 0
    collection.bulk_write(ops, ordered=False)
    written = len(ops)
    ops.clear()
    return written


def run_migration(ns: str, client: MongoClient, verbose: bool = True) -> dict:
    """Migrate one namespace. Returns per-run counters (no wall-clock values)."""
    files_db_name, quarantine_db_name = db_names(ns)
    files_db = client[files_db_name]
    quarantine_db = client[quarantine_db_name]
    shape = collection_setup.setup(files_db, quarantine_db)
    files = files_db[COLLECTION]
    quarantine = quarantine_db[QUARANTINE_COLLECTION]

    page_counts: list[int] = []
    docs: list[ReplaceOne] = []
    bad: list[ReplaceOne] = []
    migrated = quarantined = 0
    reasons: dict[str, int] = {}
    extras_attributed: dict[str, int] = {}

    for page in scan_pages(ns):
        page_counts.append(len(page))
        for item in page:
            doc, bad_doc = transform(item)
            if doc is not None:
                for attr in doc.get("extras", {}):
                    extras_attributed[attr] = extras_attributed.get(attr, 0) + 1
                docs.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            else:
                reasons[bad_doc["reason"]] = reasons.get(bad_doc["reason"], 0) + 1
                bad.append(ReplaceOne({"_id": bad_doc["_id"]}, bad_doc, upsert=True))
        # Per-batch trigger granularity: each batch commits on its own.
        if len(docs) >= BATCH_SIZE:
            migrated += _flush(files, docs)
        if len(bad) >= BATCH_SIZE:
            quarantined += _flush(quarantine, bad)
    migrated += _flush(files, docs)
    quarantined += _flush(quarantine, bad)

    scanned = sum(page_counts)
    summary = {
        "namespace": ns,
        "run_mode": run_mode(),
        "target": f"{files_db_name}.{COLLECTION}",
        "quarantine_target": f"{quarantine_db_name}.{QUARANTINE_COLLECTION}",
        "pages": len(page_counts),
        "page_counts": page_counts,
        "scanned": scanned,
        "migrated": migrated,
        "quarantined": quarantined,
        "quarantine_reasons": reasons,
        "extras_attributed": extras_attributed,
        "indexes": shape,
        "no_op": scanned == 0,
    }
    if verbose:
        if scanned == 0:
            log(f"ns={ns}: source scan empty, nothing changed (no-op)")
        else:
            log(f"ns={ns}: scanned {scanned} items over {len(page_counts)} page(s), "
                f"migrated {migrated}, quarantined {quarantined}")
    return summary


def self_test() -> None:
    """Exercise the mapping rules that the seeded estate cannot show on its own."""
    from bson import Binary

    base = {
        "id": {"S": "0f2c8d6e-0000-4000-8000-000000000001"},
        "ns": {"S": "demo"},
        "s3_key": {"S": "demo/files/owner/file"},
        "name": {"S": "réport final.pdf"},
        "updated_at": {"S": "2026-08-01T00:00:00Z"},
        "created_at": {"S": "2026-07-01T00:00:00Z"},
        "size_bytes": {"N": "250000000"},
        "is_trashed": {"BOOL": False},
        "thumbnail": {"B": b"\x00\x01\x02"},
        "legacy_flag": {"S": "keep"},
        "deleted_at": {"NULL": True},
    }
    doc, bad = transform(base)
    assert bad is None
    assert doc["size_bytes"] == 250000000 and isinstance(doc["size_bytes"], int)
    assert doc["is_trashed"] is False
    assert isinstance(doc["extras"]["thumbnail"], Binary)
    assert doc["extras"]["legacy_flag"] == "keep"
    assert "deleted_at" not in doc and "deleted_at" not in doc["extras"]
    assert doc["name"] == "réport final.pdf"  # byte-transparent, not normalised
    assert doc["orphaned_metadata"] is False

    nested = dict(base, sidecar={"M": {
        "kept": {"S": "yes"},
        "dropped": {"NULL": True},
        "order": {"L": [{"S": "a"}, {"NULL": True}, {"S": "c"}]},
    }})
    doc, _ = transform(nested)
    sidecar = doc["extras"]["sidecar"]
    assert sidecar == {"kept": "yes", "order": ["a", None, "c"]}, sidecar

    spaced = dict(base, s3_key={"S": "demo/files/owner/My Report (final).pdf"})
    doc, _ = transform(spaced)
    assert doc["storage_key"] == "demo/files/owner/My Report (final).pdf"

    orphan = dict(base, s3_key={"S": "demo/missing/owner/file"})
    doc, _ = transform(orphan)
    assert doc["orphaned_metadata"] is True

    for attr in ("ns", "s3_key", "updated_at"):
        broken = {k: v for k, v in base.items() if k != attr}
        doc, bad = transform(broken)
        assert doc is None and bad["reason"] in (
            "missing_tenant", "missing_storage_key", "missing_timestamp"), attr

    undecodable = dict(base, name={"S": "brok\udcffen.pdf"})
    doc, bad = transform(undecodable)
    assert doc is None and bad["reason"] == "invalid_encoding"
    assert bad["raw_bytes_hex"] == "62726f6bedb3bf656e2e706466"

    unparseable = dict(base, updated_at={"S": "01/15/2026"})
    doc, bad = transform(unparseable)
    assert doc is None and bad["reason"] == "invalid_timestamp"

    log("self-test: mapping, encoding and quarantine rules all hold")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--summary-out", help="write the run summary JSON here")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.ns:
        parser.error("--ns is required")

    client = MongoClient(mongo_uri())
    try:
        summary = run_migration(args.ns, client)
    finally:
        client.close()
    if args.summary_out:
        Path(args.summary_out).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
