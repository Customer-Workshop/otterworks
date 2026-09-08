"""otterworks_storage_cleanup — Airflow port of ``etl/scripts/storage_cleanup_daily.py``.

Lists the file-storage bucket, compares it with the file-metadata DynamoDB
table, quarantines orphaned objects and writes a savings report to the data
lake.

    [list_s3_objects, list_metadata_references] >> find_orphaned_objects
        >> move_to_quarantine >> generate_storage_report
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import dag, task

from otterworks.common import (
    AWS_CONN_ID,
    DEFAULT_ARGS,
    get_logger,
    get_variable,
    resolve_report_date,
    utc_now_iso,
)
from otterworks.storage_cleanup_transforms import (
    FILES_PREFIX,
    build_storage_report,
    extract_referenced_keys,
    find_orphaned_objects,
    normalize_s3_object,
    quarantine_key,
    storage_report_key,
    summarize_inventory,
)

log = get_logger(__name__)


def list_s3_objects(bucket: str, prefix: str, s3_hook: S3Hook) -> list[dict[str, Any]]:
    """Full inventory of ``s3://bucket/prefix`` as legacy inventory records."""
    objects = [normalize_s3_object(o) for o in s3_hook.get_file_metadata(prefix, bucket)]
    total_objects, total_size_bytes = summarize_inventory(objects)
    log.info(
        "s3_inventory_complete bucket=%s prefix=%s objects=%d bytes=%d",
        bucket,
        prefix,
        total_objects,
        total_size_bytes,
    )
    return objects


def list_metadata_references(table_name: str, dynamodb_hook: DynamoDBHook) -> list[str]:
    """Every ``s3_key`` referenced by the file-metadata table."""
    table = dynamodb_hook.conn.Table(table_name)
    referenced: set[str] = set()
    scan_kwargs: dict[str, Any] = {"ProjectionExpression": "s3_key"}
    pages = 0
    while True:
        response = table.scan(**scan_kwargs)
        pages += 1
        referenced |= extract_referenced_keys(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    log.info(
        "dynamodb_scan_complete table=%s pages=%d referenced_keys=%d",
        table_name,
        pages,
        len(referenced),
    )
    return sorted(referenced)


def move_to_quarantine(
    orphaned: list[dict[str, Any]],
    *,
    source_bucket: str,
    quarantine_bucket: str,
    report_date: str,
    s3_hook: S3Hook,
) -> dict[str, int]:
    """Copy each orphan to ``quarantined/<date>/<key>`` then delete the source."""
    moved = failed = 0
    for obj in orphaned:
        source_key = obj["key"]
        dest_key = quarantine_key(report_date, source_key)
        try:
            s3_hook.copy_object(
                source_bucket_key=source_key,
                dest_bucket_key=dest_key,
                source_bucket_name=source_bucket,
                dest_bucket_name=quarantine_bucket,
                meta_data_directive="COPY",
            )
            s3_hook.delete_objects(bucket=source_bucket, keys=[source_key])
            moved += 1
        except Exception:
            log.warning(
                "quarantine_failed bucket=%s key=%s dest=s3://%s/%s",
                source_bucket,
                source_key,
                quarantine_bucket,
                dest_key,
                exc_info=True,
            )
            failed += 1
    if orphaned:
        log.info(
            "quarantine_complete moved=%d failed=%d dest=s3://%s/%s/",
            moved,
            failed,
            quarantine_bucket,
            quarantine_key(report_date, "").rstrip("/"),
        )
    else:
        log.info("quarantine_skipped reason=no_orphans")
    return {"moved_count": moved, "failed_count": failed}


@dag(
    dag_id="otterworks_storage_cleanup",
    description="Quarantine orphaned S3 objects and report storage savings (daily 02:30 UTC)",
    schedule="30 2 * * *",
    start_date=datetime(2024, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"report_date": None},
    tags=["otterworks", "etl", "storage"],
    doc_md=__doc__,
)
def otterworks_storage_cleanup():
    @task(task_id="list_s3_objects")
    def list_s3_objects_task() -> list[dict[str, Any]]:
        return list_s3_objects(
            bucket=get_variable("otterworks_file_storage_bucket"),
            prefix=FILES_PREFIX,
            s3_hook=S3Hook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="list_metadata_references")
    def list_metadata_references_task() -> list[str]:
        return list_metadata_references(
            table_name=get_variable("otterworks_file_metadata_table"),
            dynamodb_hook=DynamoDBHook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="find_orphaned_objects")
    def find_orphaned_objects_task(
        objects: list[dict[str, Any]], referenced_keys: list[str]
    ) -> dict[str, Any]:
        orphaned, orphaned_bytes = find_orphaned_objects(objects, set(referenced_keys))
        total_objects, total_size_bytes = summarize_inventory(objects)
        log.info(
            "orphans_identified total_objects=%d orphaned_objects=%d orphaned_mb=%.2f",
            total_objects,
            len(orphaned),
            orphaned_bytes / (1024 * 1024),
        )
        return {
            "orphaned": orphaned,
            "orphaned_bytes": orphaned_bytes,
            "total_objects": total_objects,
            "total_size_bytes": total_size_bytes,
        }

    @task(task_id="move_to_quarantine")
    def move_to_quarantine_task(orphan_result: dict[str, Any], **context) -> dict[str, int]:
        return move_to_quarantine(
            orphan_result["orphaned"],
            source_bucket=get_variable("otterworks_file_storage_bucket"),
            quarantine_bucket=get_variable("otterworks_quarantine_bucket"),
            report_date=resolve_report_date(context),
            s3_hook=S3Hook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="generate_storage_report")
    def generate_storage_report_task(
        orphan_result: dict[str, Any], quarantine_result: dict[str, int], **context
    ) -> str:
        report_date = resolve_report_date(context)
        quarantine_bucket = get_variable("otterworks_quarantine_bucket")
        data_lake_bucket = get_variable("otterworks_data_lake_bucket")
        report = build_storage_report(
            report_date=report_date,
            generated_at=utc_now_iso(),
            total_objects=orphan_result["total_objects"],
            total_size_bytes=orphan_result["total_size_bytes"],
            orphaned_count=len(orphan_result["orphaned"]),
            orphaned_bytes=orphan_result["orphaned_bytes"],
            moved_count=quarantine_result["moved_count"],
            failed_count=quarantine_result["failed_count"],
            quarantine_bucket=quarantine_bucket,
        )
        key = storage_report_key(report_date)
        S3Hook(aws_conn_id=AWS_CONN_ID).load_bytes(
            bytes_data=json.dumps(report, indent=2).encode("utf-8"),
            key=key,
            bucket_name=data_lake_bucket,
            replace=True,
        )
        log.info(
            "storage_report_written dest=s3://%s/%s quarantined=%d freed_gb=%.4f "
            "monthly_savings_usd=%.4f",
            data_lake_bucket,
            key,
            report["cleanup"]["objects_quarantined"],
            report["savings"]["storage_freed_gb"],
            report["savings"]["estimated_monthly_savings_usd"],
        )
        return key

    objects = list_s3_objects_task()
    referenced = list_metadata_references_task()
    orphan_result = find_orphaned_objects_task(objects, referenced)
    quarantine_result = move_to_quarantine_task(orphan_result)
    generate_storage_report_task(orphan_result, quarantine_result)


otterworks_storage_cleanup()
