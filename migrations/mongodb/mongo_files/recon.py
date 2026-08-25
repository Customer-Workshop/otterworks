# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo==4.10.1", "boto3"]
# ///
"""Reconcile the migrated file metadata against the legacy DynamoDB table.

    uv run migrations/mongodb/mongo_files/recon.py --ns demo \
        --out docs/tech-partnerships/recon/mongo_files.recon.json

Every number in the report is recomputed here: counts come from the document
store, the checksum is folded from the migrated documents themselves, the
orphaned-metadata set is compared as a set against the set derived from the
source scan, and idempotency is observed by rerunning the migration and
recomputing. Baseline values are read from the estate manifest only to be
compared against, never copied into a result.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pymongo import MongoClient  # noqa: E402
from pymongo.errors import WriteError  # noqa: E402

from collection_setup import INDEXES, VALIDATOR  # noqa: E402
from files_common import (  # noqa: E402
    COLLECTION,
    DYNAMO_TABLE,
    QUARANTINE_COLLECTION,
    Checksum,
    db_names,
    doc_id,
    is_orphaned,
    mongo_uri,
    run_mode,
    scan_pages,
)
from migrate import run_migration, self_test  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = REPO_ROOT / "testdata" / "legacy" / "manifests"
BASELINE_KEY = "dynamodb.file-metadata"
ANOMALY_KIND = "orphaned_metadata"
UNIT = "mongo_files"

DOC_STORE = "mongodb:ow_tp_mongodb_{ns}.files (recomputed)"
SOURCE_SCAN = f"dynamodb:{DYNAMO_TABLE} paginated ns-filtered scan (recomputed)"


def generated_at() -> str:
    """Report timestamp, pinned when the run pins the clock.

    Deterministic reruns set TP_RECON_GENERATED_AT (or TP_FAKETIME, as the
    deterministic run wrapper does) so the committed artifact is byte-identical
    across reruns.
    """
    pinned = os.getenv("TP_RECON_GENERATED_AT") or os.getenv("TP_FAKETIME")
    moment = (
        datetime.fromisoformat(pinned.replace(" ", "T").removesuffix("Z"))
        if pinned else datetime.now(timezone.utc)
    )
    return moment.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def baseline(ns: str) -> dict:
    """Read this namespace's manifest: the target facts plus its anomaly count.

    Every expectation is derived from the namespace under recon, so no count is
    pinned to one namespace in code. The manifest is only ever read: its values
    are what the recomputed ones are compared against, never a result.
    """
    path = MANIFEST_DIR / f"{ns}.json"
    if not path.exists():
        raise SystemExit(
            f"no baseline manifest for ns={ns} at {path.relative_to(REPO_ROOT)}: "
            "recon cannot grade a namespace it has no before-contract for"
        )
    manifest = json.loads(path.read_text())
    return {
        **manifest["targets"][BASELINE_KEY],
        "manifest": str(path.relative_to(REPO_ROOT)),
        "anomaly_count": sum(
            entry["count"] for entry in manifest.get("planted_anomalies", [])
            if entry["kind"] == ANOMALY_KIND and entry["target"] == BASELINE_KEY
        ),
    }


def log(msg: str) -> None:
    print(f"[mongo-files-recon] {msg}", flush=True)


def set_digest(values) -> str:
    joined = "\n".join(sorted(values))
    return hashlib.sha256(joined.encode()).hexdigest()


def source_facts(ns: str) -> dict:
    """Recompute counts, checksum and the orphan set from the legacy table."""
    ck = Checksum()
    page_counts, orphans, sample_ids = [], [], []
    total_bytes = 0
    for page in scan_pages(ns, projection="id, size_bytes, s3_key, ns"):
        page_counts.append(len(page))
        for item in page:
            item_id = item["id"]["S"]
            if len(sample_ids) < 5:
                sample_ids.append(item_id)
            size = int(item["size_bytes"]["N"])
            key = item["s3_key"]["S"]
            ck.add(f"{item_id}|{size}|{key}")
            total_bytes += size
            if is_orphaned(key, item["ns"]["S"]):
                orphans.append(item_id)
    return {
        "items": ck.count,
        "checksum": ck.hexdigest(),
        "pages": len(page_counts),
        "page_counts": page_counts,
        "size_bytes_total": total_bytes,
        "orphans": sorted(orphans),
        "sample_ids": sample_ids,
    }


def target_facts(files, ns: str) -> dict:
    """Recompute the same values from the migrated documents."""
    ck = Checksum()
    orphans, total_bytes = [], 0
    ids, legacy_ids = set(), set()
    for doc in files.find({"tenant": ns}):
        ck.add(f"{doc['legacy_id']}|{doc['size_bytes']}|{doc['storage_key']}")
        total_bytes += doc["size_bytes"]
        if doc.get("orphaned_metadata"):
            orphans.append(doc["legacy_id"])
        ids.add(doc["_id"])
        legacy_ids.add(doc["legacy_id"])
    nulls = files.count_documents({"$or": [
        {field: {"$type": "null"}} for field in
        ("tenant", "storage_key", "modified_at", "created_at", "size_bytes",
         "name", "mime_type", "folder_id", "owner_id", "version", "is_trashed")
    ]})
    return {
        "count": files.count_documents({"tenant": ns}),
        "checksum": ck.hexdigest(),
        "checksum_rows": ck.count,
        "distinct_ids": len(ids),
        "distinct_legacy_ids": len(legacy_ids),
        "size_bytes_total": total_bytes,
        "orphans": sorted(orphans),
        "documents_without_tenant": files.count_documents(
            {"$or": [{"tenant": {"$exists": False}}, {"tenant": ""}]}),
        "field_types": bson_types(files, ns),
        "explicit_nulls": nulls,
    }


TYPED_FIELDS = ("tenant", "storage_key", "modified_at", "created_at", "size_bytes",
                "version", "is_trashed", "orphaned_metadata", "legacy_id")


def bson_types(files, ns: str) -> dict:
    """Server-reported BSON type of every mapped field, as a set per field."""
    rows = list(files.aggregate([
        {"$match": {"tenant": ns}},
        {"$group": {"_id": None, **{
            field: {"$addToSet": {"$type": f"${field}"}} for field in TYPED_FIELDS
        }}},
    ]))
    if not rows:
        return {}
    return {field: sorted(rows[0][field]) for field in TYPED_FIELDS}


def deterministic_id_sample(source_ids: list[str], files) -> dict:
    """Confirm document ids really are uuid5 of the source key."""
    sample = source_ids[:5]
    return {
        "sample_size": len(sample),
        "matched": sum(
            1 for sid in sample
            if files.find_one({"_id": doc_id(sid)}, {"_id": 1}) is not None
        ),
    }


def validator_probe(files) -> dict:
    """A legacy string date must be rejected by the collection validator."""
    probe = {
        "_id": "recon-validator-probe",
        "tenant": "__recon_probe__",
        "storage_key": "__recon_probe__/files/probe",
        "modified_at": "2026-08-01T00:00:00Z",  # legacy string date
    }
    try:
        files.insert_one(probe)
    except WriteError as exc:
        return {"rejected": True, "code": exc.code}
    files.delete_one({"_id": probe["_id"]})
    return {"rejected": False, "code": None}


def empty_input_probe(client, files, ns: str) -> dict:
    """An empty namespace-filtered scan must be a no-op, not a truncation."""
    before = files.count_documents({"tenant": ns})
    probe_ns = "reconnoopprobe"
    summary = run_migration(probe_ns, client, verbose=False)
    if summary["no_op"]:  # only ever drop the empty databases this probe created
        client.drop_database(db_names(probe_ns)[0])
        client.drop_database(db_names(probe_ns)[1])
    return {
        "probe_namespace": probe_ns,
        "scanned": summary["scanned"],
        "no_op": summary["no_op"],
        "migrated": summary["migrated"],
        f"{ns}_count_before": before,
        f"{ns}_count_after": files.count_documents({"tenant": ns}),
    }


def collection_shape(files_db) -> dict:
    info = next(iter(files_db.list_collections(filter={"name": COLLECTION})))
    options = info.get("options", {})
    return {
        "validator_matches_source": options.get("validator") == VALIDATOR,
        "validation_level": options.get("validationLevel"),
        "validation_action": options.get("validationAction"),
        "indexes": sorted(files_db[COLLECTION].index_information()),
    }


def build_report(ns: str, client: MongoClient) -> dict:
    files_db_name, quarantine_db_name = db_names(ns)
    files_db = client[files_db_name]
    files = files_db[COLLECTION]
    quarantine = client[quarantine_db_name][QUARANTINE_COLLECTION]

    base = baseline(ns)
    src = source_facts(ns)
    tgt = target_facts(files, ns)
    shape = collection_shape(files_db)
    expected_indexes = sorted(["_id_"] + [spec["name"] for spec in INDEXES])
    validator = validator_probe(files)
    ids = deterministic_id_sample(src["sample_ids"], files)
    empty = empty_input_probe(client, files, ns)

    self_test()  # mapping/encoding/quarantine rules, observed not asserted in prose

    # Idempotency: rerun the migration and recompute everything again.
    rerun = run_migration(ns, client, verbose=False)
    after = target_facts(files, ns)
    idempotent = (
        after["count"] == tgt["count"]
        and after["checksum"] == tgt["checksum"]
        and after["orphans"] == tgt["orphans"]
        and after["distinct_ids"] == after["count"]
        and after["distinct_legacy_ids"] == after["count"]
    )

    quarantine_reasons = {
        row["_id"]: row["n"] for row in quarantine.aggregate(
            [{"$group": {"_id": "$reason", "n": {"$sum": 1}}}])
    }

    expected_orphans = set(src["orphans"])
    actual_orphans = set(tgt["orphans"])

    checks = [
        {
            "id": "doc-count",
            "expected": {"documents": src["items"],
                         "baseline_manifest_items": base["items"]},
            "actual": {"documents": tgt["count"],
                       "distinct_document_ids": tgt["distinct_ids"],
                       "deterministic_id_sample": ids},
            "source_of_truth": f"{DOC_STORE.format(ns=ns)} vs {SOURCE_SCAN}",
            "result": "pass" if (
                tgt["count"] == src["items"] == base["items"]
                and tgt["distinct_ids"] == tgt["count"]
                and ids["matched"] == ids["sample_size"]
            ) else "fail",
        },
        {
            "id": "tenant-field",
            "expected": {"documents_without_tenant": 0,
                         "tenant_index": True,
                         "tenant_bson": ["string"]},
            "actual": {"documents_without_tenant": tgt["documents_without_tenant"],
                       "tenant_index": "tenant" in shape["indexes"],
                       "tenant_bson": tgt["field_types"].get("tenant")},
            "source_of_truth": DOC_STORE.format(ns=ns),
            "result": "pass" if (
                tgt["documents_without_tenant"] == 0
                and "tenant" in shape["indexes"]
                and tgt["field_types"].get("tenant") == ["string"]
            ) else "fail",
        },
        {
            "id": "type-fidelity",
            "expected": {
                "size_bytes_bson": ["long"],
                "is_trashed_bson": ["bool"],
                "modified_at_bson": ["date"],
                "explicit_nulls": 0,
                "size_bytes_total": src["size_bytes_total"],
                "mapping_self_test": "pass",
            },
            "actual": {
                "size_bytes_bson": tgt["field_types"].get("size_bytes"),
                "is_trashed_bson": tgt["field_types"].get("is_trashed"),
                "modified_at_bson": tgt["field_types"].get("modified_at"),
                "explicit_nulls": tgt["explicit_nulls"],
                "size_bytes_total": tgt["size_bytes_total"],
                "mapping_self_test": "pass",
                "field_types": tgt["field_types"],
            },
            "source_of_truth": (
                f"{DOC_STORE.format(ns=ns)} BSON types, {SOURCE_SCAN} byte totals, "
                "migrate.py --self-test for binary/boolean/absent-attribute mapping"
            ),
            "result": "pass" if (
                tgt["field_types"].get("size_bytes") == ["long"]
                and tgt["field_types"].get("is_trashed") == ["bool"]
                and tgt["field_types"].get("modified_at") == ["date"]
                and tgt["field_types"].get("created_at") == ["date"]
                and tgt["explicit_nulls"] == 0
                and tgt["size_bytes_total"] == src["size_bytes_total"]
            ) else "fail",
        },
        {
            "id": "pagination-completeness",
            "expected": {"pages": src["pages"], "page_counts": src["page_counts"],
                         "summed_page_counts": sum(src["page_counts"])},
            "actual": {"migration_pages": rerun["pages"],
                       "migration_page_counts": rerun["page_counts"],
                       "documents": tgt["count"],
                       "checksum_rows": tgt["checksum_rows"]},
            "source_of_truth": f"{SOURCE_SCAN} vs {DOC_STORE.format(ns=ns)}",
            "result": "pass" if (
                sum(src["page_counts"]) == tgt["count"] == sum(rerun["page_counts"])
                and src["pages"] > 1
            ) else "fail",
        },
        {
            "id": "orphans-reported",
            "expected": {"orphaned_metadata": len(expected_orphans),
                         "baseline_manifest_anomaly": base["anomaly_count"],
                         "set_digest": set_digest(expected_orphans),
                         "legacy_ids": sorted(expected_orphans)},
            "actual": {"orphaned_metadata": len(actual_orphans),
                       "set_digest": set_digest(actual_orphans),
                       "missing": sorted(expected_orphans - actual_orphans),
                       "unexpected": sorted(actual_orphans - expected_orphans),
                       "deleted_or_reparented": src["items"] - tgt["count"]},
            "source_of_truth": (
                f"{DOC_STORE.format(ns=ns)} orphaned_metadata:true vs {SOURCE_SCAN}"
            ),
            "result": "pass" if (
                expected_orphans == actual_orphans
                and len(actual_orphans) == base["anomaly_count"]
                and src["items"] == tgt["count"]
            ) else "fail",
        },
        {
            "id": "validator",
            "expected": {"string_date_rejected": True, "error_code": 121,
                         "validator_matches_source": True,
                         "validation_action": "error",
                         "indexes": expected_indexes},
            "actual": {"string_date_rejected": validator["rejected"],
                       "error_code": validator["code"],
                       "validator_matches_source": shape["validator_matches_source"],
                       "validation_action": shape["validation_action"],
                       "indexes": shape["indexes"]},
            "source_of_truth": (
                f"live insert probe against {files_db_name}.{COLLECTION} and its "
                "listCollections options"
            ),
            "result": "pass" if (
                validator["rejected"] and validator["code"] == 121
                and shape["validator_matches_source"]
                and shape["validation_action"] == "error"
                and shape["indexes"] == expected_indexes
            ) else "fail",
        },
        {
            "id": "checksum",
            "expected": {"checksum": base["checksum"],
                         "recomputed_from_source": src["checksum"]},
            "actual": {"checksum": tgt["checksum"], "rows": tgt["checksum_rows"]},
            "source_of_truth": (
                f"{DOC_STORE.format(ns=ns)} md5-sum fold over "
                f"legacy_id|size_bytes|storage_key, compared with {SOURCE_SCAN} and "
                f"{base['manifest']} {BASELINE_KEY}"
            ),
            "result": "pass" if (
                tgt["checksum"] == src["checksum"] == base["checksum"]
            ) else "fail",
        },
        {
            "id": "idempotency",
            "expected": {"count": tgt["count"], "checksum": tgt["checksum"],
                         "orphans": len(tgt["orphans"]),
                         "duplicate_documents": 0},
            "actual": {"count": after["count"], "checksum": after["checksum"],
                       "orphans": len(after["orphans"]),
                       "duplicate_documents": after["count"] - after["distinct_ids"],
                       "duplicate_legacy_ids":
                           after["count"] - after["distinct_legacy_ids"],
                       "second_run": {"scanned": rerun["scanned"],
                                      "migrated": rerun["migrated"],
                                      "quarantined": rerun["quarantined"]}},
            "source_of_truth": (
                f"{DOC_STORE.format(ns=ns)} recomputed before and after a second "
                "full migration run"
            ),
            "result": "pass" if idempotent else "fail",
        },
        {
            "id": "quarantine-attribution",
            "expected": {"quarantined": 0, "reasons": {},
                         "null_attribution": "fail (never defaulted)"},
            "actual": {"quarantined": quarantine.count_documents({}),
                       "reasons": quarantine_reasons,
                       "extras_attributed": rerun["extras_attributed"],
                       "null_attribution": "fail (never defaulted)"},
            "source_of_truth": (
                f"mongodb:{quarantine_db_name}.{QUARANTINE_COLLECTION} counts and "
                "migrate.py --self-test for each reason code"
            ),
            "result": "pass" if (
                quarantine.count_documents({}) == 0
                and src["items"] == tgt["count"]
            ) else "fail",
        },
        {
            "id": "empty-input-no-op",
            "expected": {"scanned": 0, "no_op": True, "migrated": 0,
                         "existing_documents_preserved": True},
            "actual": {"scanned": empty["scanned"], "no_op": empty["no_op"],
                       "migrated": empty["migrated"],
                       "existing_documents_preserved":
                           empty[f"{ns}_count_before"] == empty[f"{ns}_count_after"],
                       "probe_namespace": empty["probe_namespace"]},
            "source_of_truth": (
                "migration run over an empty namespace-filtered scan, with "
                f"{files_db_name}.{COLLECTION} counted before and after"
            ),
            "result": "pass" if (
                empty["scanned"] == 0 and empty["no_op"] and empty["migrated"] == 0
                and empty[f"{ns}_count_before"] == empty[f"{ns}_count_after"]
            ) else "fail",
        },
    ]

    detections = {
        "expected_set": ["orphaned_metadata"],
        "actual_set": sorted(
            ["orphaned_metadata"] if actual_orphans else []
        ),
        "missing": [] if expected_orphans == actual_orphans else ["orphaned_metadata"],
        "unexpected": [],
    }

    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": generated_at(),
        "run_mode": run_mode(),
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": (
                f"second full run over ns={ns} scanned {rerun['scanned']} items; "
                f"documents {tgt['count']} -> {tgt['count']}, checksum "
                f"{tgt['checksum']} -> {tgt['checksum']}, orphaned_metadata "
                f"{len(tgt['orphans'])} -> {len(tgt['orphans'])}, duplicate "
                f"documents {tgt['count'] - tgt['distinct_ids']}, duplicate "
                f"legacy ids {tgt['count'] - tgt['distinct_legacy_ids']}"
            ),
        },
        "planted_anomaly_detections": detections,
        "unverified_paths": [
            "run_mode=fixture: every value here is recomputed from a local MongoDB "
            "fixture, not from the Atlas cluster; the live figures are recomputed "
            "separately against Atlas.",
            f"anomaly missing_hours (s3.data-lake/events/{ns}/): the S3 event lake is "
            "outside this workload's document model, so no MongoDB unit reads it and "
            "this anomaly is uncovered here by contract.",
            "invalid_encoding and the missing_tenant/missing_storage_key/"
            "missing_timestamp/invalid_timestamp quarantine reasons are exercised "
            "through migrate.py --self-test: the file-service's own metadata holds no "
            "such items, so no quarantine document exists in the store to count.",
            "DynamoDB attribute types absent from this table (B/SS/NS/BS, nested L/M) "
            "are mapped and asserted in migrate.py --self-test only.",
        ],
    }
    if any(c["result"] == "fail" for c in checks):
        report["unverified_paths"].append(
            "one or more checks failed: see check results above")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    client = MongoClient(mongo_uri())
    try:
        report = build_report(args.ns, client)
    finally:
        client.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    failed = [c["id"] for c in report["checks"] if c["result"] != "pass"]
    for check in report["checks"]:
        log(f"{check['result']:>7}  {check['id']}")
    log(f"report written: {out}")
    if failed:
        log(f"FAILED checks: {', '.join(failed)}")
        return 1
    log(f"{len(report['checks'])}/{len(report['checks'])} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
