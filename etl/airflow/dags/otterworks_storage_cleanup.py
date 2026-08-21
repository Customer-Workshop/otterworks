"""Daily orphaned-S3-object cleanup.

Reference migration of ``etl/scripts/storage_cleanup_daily.py`` (cron
``30 2 * * *``). This DAG is the pattern the rest of the estate copies:

* one ``PythonOperator`` per stage, independent extracts running in parallel;
* all IO through provider hooks bound to named Connections;
* configuration from Airflow Variables resolved inside the task callables;
* pure, importable transform functions that the pytest suite exercises
  without any AWS access;
* the logical date (``ds``) — not ``datetime.now()`` — keys every write, so a
  re-run or a backfill reproduces the same objects instead of new ones.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from airflow import DAG
from airflow.operators.python import PythonOperator

from common.config import (
    VAR_DATA_LAKE_BUCKET,
    VAR_FILE_METADATA_TABLE,
    VAR_FILE_STORAGE_BUCKET,
    VAR_QUARANTINE_BUCKET,
    get_var,
)
from common.defaults import dag_kwargs
from common.hooks import (
    get_dynamodb_table,
    get_s3_hook,
    put_json_object,
    run_with_failure_summary,
    scan_dynamodb_table,
)
from common.logging_utils import get_logger

log = get_logger(__name__)

DAG_ID = "otterworks_storage_cleanup"
FILES_PREFIX = "files/"
QUARANTINE_PREFIX = "quarantined"
REPORT_KEY_TEMPLATE = "reports/storage-cleanup/{ds}/report.json"

#: Price per GB-month used by the legacy savings estimate (S3 Standard).
GB_MONTH_USD = 0.023
BYTES_PER_GB = 1024**3


# ---------------------------------------------------------------------------
# Pure functions (unit-tested without AWS)
# ---------------------------------------------------------------------------
def find_orphans(
    objects: list[dict[str, Any]], referenced_keys: list[str]
) -> dict[str, Any]:
    """Split an S3 inventory into referenced and orphaned objects."""
    referenced = set(referenced_keys)
    orphaned = [obj for obj in objects if obj["key"] not in referenced]
    return {
        "orphaned": orphaned,
        "orphaned_count": len(orphaned),
        "orphaned_bytes": sum(obj["size"] for obj in orphaned),
    }


def quarantine_key(ds: str, source_key: str) -> str:
    """Destination key for a quarantined object, partitioned by logical date."""
    return f"{QUARANTINE_PREFIX}/{ds}/{source_key}"


def build_report(
    *,
    ds: str,
    generated_at: str,
    total_objects: int,
    total_size_bytes: int,
    orphaned_count: int,
    orphaned_bytes: int,
    moved_count: int,
    failed_count: int,
    quarantine_bucket: str,
) -> dict[str, Any]:
    """Build the storage-cleanup report (same shape as the legacy script)."""
    savings_gb = orphaned_bytes / BYTES_PER_GB
    return {
        "report_type": "storage_cleanup",
        "report_date": ds,
        "generated_at": generated_at,
        "inventory": {
            "total_objects": total_objects,
            "total_size_bytes": total_size_bytes,
            "total_size_gb": round(total_size_bytes / BYTES_PER_GB, 4),
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
            "estimated_monthly_savings_usd": round(savings_gb * GB_MONTH_USD, 4),
        },
    }


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------
def list_s3_objects() -> dict[str, Any]:
    """Inventory the file-storage bucket under ``files/``."""
    bucket = get_var(VAR_FILE_STORAGE_BUCKET)
    hook = get_s3_hook()
    paginator = hook.get_conn().get_paginator("list_objects_v2")

    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=FILES_PREFIX):
        for obj in page.get("Contents", []):
            objects.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )

    total_size = sum(obj["size"] for obj in objects)
    log.info("Found %d objects in s3://%s/%s (%d bytes)", len(objects), bucket, FILES_PREFIX, total_size)
    return {"objects": objects, "total_objects": len(objects), "total_size_bytes": total_size}


def list_metadata_references() -> list[str]:
    """Collect every ``s3_key`` referenced by the file-metadata table."""
    table_name = get_var(VAR_FILE_METADATA_TABLE)
    table = get_dynamodb_table(table_name)

    keys = {
        item["s3_key"]
        for item in scan_dynamodb_table(table, ProjectionExpression="s3_key")
        if item.get("s3_key")
    }
    log.info("Found %d S3 keys referenced in %s", len(keys), table_name)
    return sorted(keys)


def find_orphaned_objects(ti: Any) -> dict[str, Any]:
    inventory = ti.xcom_pull(task_ids="list_s3_objects")
    referenced = ti.xcom_pull(task_ids="list_metadata_references")
    result = find_orphans(inventory["objects"], referenced)
    log.info(
        "Found %d orphaned objects (%.2f MB)",
        result["orphaned_count"],
        result["orphaned_bytes"] / (1024 * 1024),
    )
    return result


def move_to_quarantine(ti: Any, ds: str) -> int:
    """Copy each orphan into the quarantine bucket, then delete the original.

    Any failure fails the task (the legacy script counted failures, logged a
    warning and exited 0). A task retry re-reads the same upstream XCom rather
    than re-listing the bucket, so an object moved before an earlier attempt
    failed is still in the list: a source key that no longer exists means the
    move already happened and counts as quarantined.
    """
    orphans = ti.xcom_pull(task_ids="find_orphaned_objects")["orphaned"]
    if not orphans:
        log.info("No orphaned objects to quarantine")
        return 0

    source_bucket = get_var(VAR_FILE_STORAGE_BUCKET)
    quarantine_bucket = get_var(VAR_QUARANTINE_BUCKET)
    client = get_s3_hook().get_conn()

    def quarantine(obj: dict[str, Any]) -> None:
        source_key = obj["key"]
        try:
            client.head_object(Bucket=source_bucket, Key=source_key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                raise
            log.info("%s was already quarantined by an earlier attempt", source_key)
            return

        client.copy_object(
            Bucket=quarantine_bucket,
            Key=quarantine_key(ds, source_key),
            CopySource={"Bucket": source_bucket, "Key": source_key},
            MetadataDirective="COPY",
        )
        client.delete_object(Bucket=source_bucket, Key=source_key)

    outcome = run_with_failure_summary(orphans, quarantine, description="quarantine")
    log.info(
        "Quarantined %d objects to s3://%s/%s/%s/",
        outcome["succeeded"],
        quarantine_bucket,
        QUARANTINE_PREFIX,
        ds,
    )
    return int(outcome["succeeded"])


def generate_storage_report(ti: Any, ds: str, ts: str) -> str:
    inventory = ti.xcom_pull(task_ids="list_s3_objects")
    orphans = ti.xcom_pull(task_ids="find_orphaned_objects")
    moved_count = ti.xcom_pull(task_ids="move_to_quarantine") or 0

    report = build_report(
        ds=ds,
        generated_at=ts,
        total_objects=inventory["total_objects"],
        total_size_bytes=inventory["total_size_bytes"],
        orphaned_count=orphans["orphaned_count"],
        orphaned_bytes=orphans["orphaned_bytes"],
        moved_count=moved_count,
        failed_count=0,
        quarantine_bucket=get_var(VAR_QUARANTINE_BUCKET),
    )
    key = put_json_object(
        get_var(VAR_DATA_LAKE_BUCKET), REPORT_KEY_TEMPLATE.format(ds=ds), report
    )
    log.info(
        "Storage cleanup report: %d orphans quarantined, %.4f GB freed, ~$%.4f/month saved",
        moved_count,
        report["savings"]["storage_freed_gb"],
        report["savings"]["estimated_monthly_savings_usd"],
    )
    return key


with DAG(
    dag_id=DAG_ID,
    description="Quarantine orphaned S3 objects and report the storage freed",
    schedule="30 2 * * *",
    doc_md=__doc__,
    **dag_kwargs(),
) as dag:
    list_objects_task = PythonOperator(
        task_id="list_s3_objects",
        python_callable=list_s3_objects,
    )
    list_metadata_task = PythonOperator(
        task_id="list_metadata_references",
        python_callable=list_metadata_references,
    )
    find_orphans_task = PythonOperator(
        task_id="find_orphaned_objects",
        python_callable=find_orphaned_objects,
    )
    quarantine_task = PythonOperator(
        task_id="move_to_quarantine",
        python_callable=move_to_quarantine,
    )
    report_task = PythonOperator(
        task_id="generate_storage_report",
        python_callable=generate_storage_report,
    )

    [list_objects_task, list_metadata_task] >> find_orphans_task
    find_orphans_task >> quarantine_task >> report_task
