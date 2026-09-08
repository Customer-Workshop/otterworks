"""Pure transformation logic for the storage cleanup pipeline.

Behaviour mirrors ``etl/scripts/storage_cleanup_daily.py`` exactly (key
formats, orphan detection, report layout and savings math) but has no AWS or
Airflow dependencies so it can be unit tested in isolation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

FILES_PREFIX = "files/"
QUARANTINE_PREFIX = "quarantined"
S3_STANDARD_USD_PER_GB_MONTH = 0.023

S3Object = dict[str, Any]


def normalize_s3_object(obj: dict[str, Any]) -> S3Object:
    """Project a ``list_objects_v2`` entry to the legacy inventory record."""
    last_modified = obj["LastModified"]
    if isinstance(last_modified, datetime):
        last_modified = last_modified.isoformat()
    return {"key": obj["Key"], "size": obj["Size"], "last_modified": last_modified}


def summarize_inventory(objects: list[S3Object]) -> tuple[int, int]:
    """Return ``(total_objects, total_size_bytes)``."""
    return len(objects), sum(o["size"] for o in objects)


def extract_referenced_keys(items: list[dict[str, Any]]) -> set[str]:
    """Collect non-empty ``s3_key`` attributes from DynamoDB metadata items."""
    return {item["s3_key"] for item in items if item.get("s3_key")}


def find_orphaned_objects(
    objects: list[S3Object], referenced_keys: set[str]
) -> tuple[list[S3Object], int]:
    """Objects whose key has no metadata reference, plus their total bytes."""
    orphaned = [o for o in objects if o["key"] not in referenced_keys]
    return orphaned, sum(o["size"] for o in orphaned)


def quarantine_key(report_date: str, source_key: str) -> str:
    return f"{QUARANTINE_PREFIX}/{report_date}/{source_key}"


def storage_report_key(report_date: str) -> str:
    return f"reports/storage-cleanup/{report_date}/report.json"


def build_storage_report(
    *,
    report_date: str,
    generated_at: str,
    total_objects: int,
    total_size_bytes: int,
    orphaned_count: int,
    orphaned_bytes: int,
    moved_count: int,
    failed_count: int,
    quarantine_bucket: str,
) -> dict[str, Any]:
    savings_gb = orphaned_bytes / (1024**3)
    estimated_monthly_savings = round(savings_gb * S3_STANDARD_USD_PER_GB_MONTH, 4)
    return {
        "report_type": "storage_cleanup",
        "report_date": report_date,
        "generated_at": generated_at,
        "inventory": {
            "total_objects": total_objects,
            "total_size_bytes": total_size_bytes,
            "total_size_gb": round(total_size_bytes / (1024**3), 4),
        },
        "orphans": {
            "orphaned_objects": orphaned_count,
            "orphaned_bytes": orphaned_bytes,
            "orphaned_size_gb": round(savings_gb, 4),
            "orphan_percentage": round(
                (orphaned_count / total_objects * 100) if total_objects else 0, 2
            ),
        },
        "cleanup": {
            "objects_quarantined": moved_count,
            "objects_failed": failed_count,
            "quarantine_bucket": quarantine_bucket,
        },
        "savings": {
            "storage_freed_gb": round(savings_gb, 4),
            "estimated_monthly_savings_usd": estimated_monthly_savings,
        },
    }
