"""Storage cleanup business logic for the ``otterworks_storage_cleanup`` DAG.

The stage functions here are deliberately hook-agnostic: they take an already
constructed ``S3Hook`` / ``DynamoDBHook`` / ``PostgresHook`` so they can be unit
tested against mocked hooks (or moto-backed real hooks).

Error policy: no exception is swallowed. Anything that goes wrong propagates so
the Airflow task fails and is retried with exponential backoff.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

from otterworks_etl.config import STORAGE_COST_PER_GB_MONTH, StorageCleanupConfig

logger = logging.getLogger(__name__)

GIB = 1024**3
MIB = 1024**2

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    report_date DATE NOT NULL,
    s3_key TEXT NOT NULL,
    quarantine_key TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (report_date, s3_key)
)
"""


def list_s3_objects(s3_hook: Any, config: StorageCleanupConfig) -> list[dict[str, Any]]:
    """Inventory every object under the configured files prefix.

    Key and size both come from the ``list_objects_v2`` pages, so the inventory
    costs one request per page rather than an extra HEAD per object.
    """
    paginator = s3_hook.get_conn().get_paginator("list_objects_v2")
    pages = paginator.paginate(
        Bucket=config.file_storage_bucket, Prefix=config.files_prefix
    )

    objects: list[dict[str, Any]] = []
    for page in pages:
        for entry in page.get("Contents", []):
            key = entry["Key"]
            if key.endswith("/"):
                # Zero-byte directory markers are not real objects.
                continue
            objects.append({"key": key, "size": int(entry["Size"])})

    total_bytes = sum(obj["size"] for obj in objects)
    logger.info(
        "Inventoried %d objects (%d bytes) in s3://%s/%s",
        len(objects),
        total_bytes,
        config.file_storage_bucket,
        config.files_prefix,
    )
    return objects


def list_metadata_references(dynamodb_hook: Any, config: StorageCleanupConfig) -> list[str]:
    """Scan the file-metadata table and return every referenced S3 key."""
    table = dynamodb_hook.get_conn().Table(config.metadata_table)

    referenced: set[str] = set()
    scan_kwargs: dict[str, Any] = {"ProjectionExpression": "s3_key"}
    pages = 0
    while True:
        response = table.scan(**scan_kwargs)
        pages += 1
        for item in response.get("Items", []):
            s3_key = item.get("s3_key")
            if s3_key:
                referenced.add(str(s3_key))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info(
        "Scanned %s over %d page(s); %d referenced S3 keys",
        config.metadata_table,
        pages,
        len(referenced),
    )
    return sorted(referenced)


def find_orphaned_objects(
    objects: Iterable[dict[str, Any]], referenced_keys: Iterable[str]
) -> dict[str, Any]:
    """Diff the S3 inventory against metadata references.

    Objects present in S3 with no metadata row are orphans. Metadata rows with
    no object are dangling references: they are reported (they indicate an
    upstream data-quality problem) but nothing is deleted for them.
    """
    referenced = set(referenced_keys)
    inventory = list(objects)
    present_keys = {obj["key"] for obj in inventory}

    orphans = sorted(
        (obj for obj in inventory if obj["key"] not in referenced), key=lambda obj: obj["key"]
    )
    dangling = sorted(referenced - present_keys)

    orphaned_bytes = sum(obj["size"] for obj in orphans)
    total_bytes = sum(obj["size"] for obj in inventory)

    if dangling:
        logger.warning(
            "%d metadata reference(s) point at missing objects, e.g. %s",
            len(dangling),
            dangling[:5],
        )
    if not inventory:
        logger.info("Source bucket inventory is empty; nothing to quarantine")

    logger.info(
        "Found %d orphaned object(s) (%.2f MiB) out of %d inventoried",
        len(orphans),
        orphaned_bytes / MIB,
        len(inventory),
    )
    return {
        "orphans": orphans,
        "orphaned_bytes": orphaned_bytes,
        "dangling_references": dangling,
        "total_objects": len(inventory),
        "total_size_bytes": total_bytes,
    }


def quarantine_key_for(config: StorageCleanupConfig, ds: str, source_key: str) -> str:
    return f"{config.quarantine_prefix}/{ds}/{source_key}"


def move_to_quarantine(
    s3_hook: Any,
    postgres_hook: Any,
    config: StorageCleanupConfig,
    orphans: Sequence[dict[str, Any]],
    ds: str,
) -> dict[str, Any]:
    """Copy orphans into the dated quarantine prefix and delete the originals.

    Idempotency: the destination key is derived from the logical date, and an
    object already present at that destination is skipped rather than copied
    again. The Postgres ledger insert is ``ON CONFLICT DO NOTHING`` on
    ``(report_date, s3_key)``, so re-running the same logical date neither
    double-quarantines nor duplicates rows.
    """
    postgres_hook.run(LEDGER_DDL.format(table=config.ledger_table))

    moved: list[dict[str, Any]] = []
    skipped: list[str] = []

    for obj in orphans:
        source_key = obj["key"]
        dest_key = quarantine_key_for(config, ds, source_key)

        if s3_hook.check_for_key(key=dest_key, bucket_name=config.quarantine_bucket):
            logger.info("Orphan %s already quarantined at %s; skipping", source_key, dest_key)
            skipped.append(source_key)
        else:
            s3_hook.copy_object(
                source_bucket_key=source_key,
                dest_bucket_key=dest_key,
                source_bucket_name=config.file_storage_bucket,
                dest_bucket_name=config.quarantine_bucket,
            )
            moved.append({"key": source_key, "size": obj["size"], "quarantine_key": dest_key})

        # Deleting an already-absent key is a no-op, which keeps replays safe.
        s3_hook.delete_objects(bucket=config.file_storage_bucket, keys=[source_key])

        postgres_hook.run(
            f"INSERT INTO {config.ledger_table} "
            "(report_date, s3_key, quarantine_key, size_bytes) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (report_date, s3_key) DO NOTHING",
            parameters=(ds, source_key, dest_key, obj["size"]),
        )

    moved_bytes = sum(item["size"] for item in moved)
    logger.info(
        "Quarantined %d object(s) (%d already present, skipped) into s3://%s/%s/%s/",
        len(moved),
        len(skipped),
        config.quarantine_bucket,
        config.quarantine_prefix,
        ds,
    )
    return {
        "objects_quarantined": len(moved),
        "objects_skipped": len(skipped),
        "bytes_quarantined": moved_bytes,
        "quarantined_keys": [item["quarantine_key"] for item in moved],
        "skipped_keys": skipped,
    }


def build_report(
    config: StorageCleanupConfig,
    ds: str,
    diff: dict[str, Any],
    quarantine_result: dict[str, Any],
) -> dict[str, Any]:
    """Build the deterministic storage-cleanup report for a logical date."""
    total_objects = diff["total_objects"]
    orphaned_bytes = diff["orphaned_bytes"]
    savings_gb = orphaned_bytes / GIB

    return {
        "report_type": "storage_cleanup",
        "report_date": ds,
        "inventory": {
            "total_objects": total_objects,
            "total_size_bytes": diff["total_size_bytes"],
            "total_size_gb": round(diff["total_size_bytes"] / GIB, 4),
        },
        "orphans": {
            "orphaned_objects": len(diff["orphans"]),
            "orphaned_bytes": orphaned_bytes,
            "orphaned_size_gb": round(savings_gb, 4),
            "orphan_percentage": round(
                (len(diff["orphans"]) / total_objects * 100) if total_objects else 0.0, 2
            ),
            "dangling_references": len(diff["dangling_references"]),
        },
        "cleanup": {
            "objects_quarantined": quarantine_result["objects_quarantined"],
            "objects_skipped": quarantine_result["objects_skipped"],
            "quarantine_bucket": config.quarantine_bucket,
        },
        "savings": {
            "storage_freed_gb": round(savings_gb, 4),
            "estimated_monthly_savings_usd": round(savings_gb * STORAGE_COST_PER_GB_MONTH, 4),
        },
    }


def report_key_for(ds: str) -> str:
    return f"reports/storage-cleanup/{ds}/report.json"


def publish_report(s3_hook: Any, config: StorageCleanupConfig, report: dict[str, Any]) -> str:
    """Write the report to a per-logical-date key, replacing any previous run."""
    key = report_key_for(report["report_date"])
    s3_hook.load_string(
        string_data=json.dumps(report, indent=2, sort_keys=True),
        key=key,
        bucket_name=config.data_lake_bucket,
        replace=True,
    )
    logger.info(
        "Published storage cleanup report to s3://%s/%s: %d orphan(s), %s GB freed, ~$%s/month",
        config.data_lake_bucket,
        key,
        report["orphans"]["orphaned_objects"],
        report["savings"]["storage_freed_gb"],
        report["savings"]["estimated_monthly_savings_usd"],
    )
    return key
