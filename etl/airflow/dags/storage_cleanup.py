"""
OtterWorks Storage Cleanup Pipeline

Daily storage maintenance that finds orphaned S3 objects (no metadata
reference in DynamoDB), moves them to a quarantine bucket, and reports
storage savings.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

logger = logging.getLogger(__name__)

# Configuration
FILES_BUCKET = "{{ var.value.get('otterworks_files_bucket', 'otterworks-file-storage') }}"
QUARANTINE_BUCKET = "{{ var.value.get('otterworks_quarantine_bucket', 'otterworks-file-quarantine') }}"
REPORT_BUCKET = "{{ var.value.get('otterworks_data_lake_bucket', 'otterworks-data-lake') }}"
DYNAMODB_TABLE = "otterworks-file-metadata"
FILES_PREFIX = "files/"
AWS_CONN_ID = "aws_default"
QUARANTINE_PREFIX = "quarantined"
S3_LIST_PAGE_SIZE = 1000

default_args = {
    "owner": "otterworks-platform",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def list_s3_objects(**context):
    """List all objects in the files S3 bucket.

    Paginates through the entire bucket to build a complete inventory
    of S3 keys and their sizes.
    """
    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    s3_client = s3_hook.get_conn()

    all_objects = []
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=FILES_BUCKET, Prefix=FILES_PREFIX):
        for obj in page.get("Contents", []):
            all_objects.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )

    logger.info("Found %d objects in s3://%s/%s", len(all_objects), FILES_BUCKET, FILES_PREFIX)
    context["ti"].xcom_push(key="total_objects", value=len(all_objects))
    context["ti"].xcom_push(key="total_size_bytes", value=sum(o["size"] for o in all_objects))
    return all_objects


def list_metadata_references(**context):
    """Query DynamoDB file-metadata table to get all known S3 keys.

    Builds a set of S3 keys that are referenced in file metadata,
    which will be used to identify orphaned objects.
    """
    import boto3

    session = boto3.Session()
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE)

    referenced_keys = set()
    scan_kwargs = {
        "ProjectionExpression": "s3_key",
    }

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            s3_key = item.get("s3_key", "")
            if s3_key:
                referenced_keys.add(s3_key)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info("Found %d S3 keys referenced in metadata", len(referenced_keys))
    return list(referenced_keys)


def find_orphaned_objects(**context):
    """Compare S3 inventory with metadata references to find orphans.

    An orphaned object is one that exists in S3 but has no corresponding
    entry in the file metadata DynamoDB table.
    """
    s3_objects = context["ti"].xcom_pull(task_ids="list_s3_objects") or []
    referenced_keys = set(context["ti"].xcom_pull(task_ids="list_metadata_references") or [])

    orphaned = []
    orphaned_bytes = 0

    for obj in s3_objects:
        if obj["key"] not in referenced_keys:
            orphaned.append(obj)
            orphaned_bytes += obj["size"]

    logger.info(
        "Found %d orphaned objects (%.2f MB)",
        len(orphaned),
        orphaned_bytes / (1024 * 1024),
    )

    context["ti"].xcom_push(key="orphaned_count", value=len(orphaned))
    context["ti"].xcom_push(key="orphaned_bytes", value=orphaned_bytes)
    return orphaned


def move_to_quarantine(**context):
    """Move orphaned objects to the quarantine bucket.

    Copies each orphaned object to the quarantine bucket with a
    date-prefixed key, then deletes the original. This allows
    recovery if an object was incorrectly identified as orphaned.
    """
    orphaned = context["ti"].xcom_pull(task_ids="find_orphaned_objects") or []
    if not orphaned:
        logger.info("No orphaned objects to quarantine")
        return

    ds = context["ds"]
    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    s3_client = s3_hook.get_conn()

    moved_count = 0
    failed_count = 0

    for obj in orphaned:
        source_key = obj["key"]
        dest_key = f"{QUARANTINE_PREFIX}/{ds}/{source_key}"

        try:
            s3_client.copy_object(
                Bucket=QUARANTINE_BUCKET,
                Key=dest_key,
                CopySource={"Bucket": FILES_BUCKET, "Key": source_key},
                MetadataDirective="COPY",
            )
            s3_client.delete_object(Bucket=FILES_BUCKET, Key=source_key)
            moved_count += 1
        except Exception as exc:
            logger.warning("Failed to quarantine %s: %s", source_key, exc)
            failed_count += 1

    logger.info(
        "Quarantined %d objects (%d failed) to s3://%s/%s/%s/",
        moved_count,
        failed_count,
        QUARANTINE_BUCKET,
        QUARANTINE_PREFIX,
        ds,
    )

    context["ti"].xcom_push(key="moved_count", value=moved_count)
    context["ti"].xcom_push(key="failed_count", value=failed_count)


def generate_storage_report(**context):
    """Generate a storage cleanup report with savings information.

    The report includes inventory totals, orphan counts, and
    estimated storage savings from the cleanup operation.
    """
    ds = context["ds"]
    total_objects = context["ti"].xcom_pull(key="total_objects", task_ids="list_s3_objects") or 0
    total_size = context["ti"].xcom_pull(key="total_size_bytes", task_ids="list_s3_objects") or 0
    orphaned_count = context["ti"].xcom_pull(
        key="orphaned_count", task_ids="find_orphaned_objects"
    ) or 0
    orphaned_bytes = context["ti"].xcom_pull(
        key="orphaned_bytes", task_ids="find_orphaned_objects"
    ) or 0
    moved_count = context["ti"].xcom_pull(key="moved_count", task_ids="move_to_quarantine") or 0
    failed_count = context["ti"].xcom_pull(key="failed_count", task_ids="move_to_quarantine") or 0

    # Estimate monthly savings (S3 Standard: ~$0.023/GB/month)
    savings_gb = orphaned_bytes / (1024 ** 3)
    estimated_monthly_savings = round(savings_gb * 0.023, 4)

    report = {
        "report_type": "storage_cleanup",
        "report_date": ds,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "inventory": {
            "total_objects": total_objects,
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024 ** 3), 4),
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
            "quarantine_bucket": QUARANTINE_BUCKET,
        },
        "savings": {
            "storage_freed_gb": round(savings_gb, 4),
            "estimated_monthly_savings_usd": estimated_monthly_savings,
        },
    }

    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    report_key = f"reports/storage-cleanup/{ds}/report.json"
    s3_hook.load_string(
        json.dumps(report, indent=2),
        key=report_key,
        bucket_name=REPORT_BUCKET,
        replace=True,
    )

    logger.info(
        "Storage cleanup report: %d orphans quarantined, %.4f GB freed, ~$%.4f/month saved",
        moved_count,
        savings_gb,
        estimated_monthly_savings,
    )


with DAG(
    "otterworks_storage_cleanup",
    default_args=default_args,
    description="Daily storage maintenance: find orphaned S3 objects, quarantine, report savings",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "storage", "maintenance", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    list_objects = PythonOperator(
        task_id="list_s3_objects",
        python_callable=list_s3_objects,
    )

    list_metadata = PythonOperator(
        task_id="list_metadata_references",
        python_callable=list_metadata_references,
    )

    find_orphans = PythonOperator(
        task_id="find_orphaned_objects",
        python_callable=find_orphaned_objects,
    )

    quarantine = PythonOperator(
        task_id="move_to_quarantine",
        python_callable=move_to_quarantine,
    )

    report = PythonOperator(
        task_id="generate_storage_report",
        python_callable=generate_storage_report,
    )

    # List S3 objects and metadata in parallel, find orphans, quarantine, report
    [list_objects, list_metadata] >> find_orphans >> quarantine >> report
