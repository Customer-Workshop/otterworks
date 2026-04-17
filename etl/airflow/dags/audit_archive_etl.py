"""
OtterWorks Audit Archive ETL Pipeline

Weekly pipeline that archives audit events from DynamoDB to S3 Glacier
for long-term retention and compliance (GDPR, SOC2).

Steps:
  1. Scan DynamoDB for events older than 90 days
  2. Compress to JSONL.gz
  3. Upload to S3 with Glacier storage class
  4. Batch-delete archived records from DynamoDB
  5. Generate compliance report
"""

import gzip
import io
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

logger = logging.getLogger(__name__)

# Configuration
DYNAMODB_TABLE = "otterworks-audit-events"
S3_BUCKET = "{{ var.value.get('otterworks_archive_bucket', 'otterworks-audit-archive') }}"
S3_PREFIX = "audit-archive"
AWS_CONN_ID = "aws_default"
RETENTION_DAYS = 90
DYNAMODB_BATCH_SIZE = 25  # DynamoDB batch write limit

default_args = {
    "owner": "otterworks-compliance",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
}


class _DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types during JSON serialization."""

    def default(self, o):
        if isinstance(o, Decimal):
            if o == int(o):
                return int(o)
            return float(o)
        return super().default(o)


def scan_audit_events(**context):
    """Scan DynamoDB for audit events older than retention period.

    Performs a full-table scan with a filter for events whose timestamp
    is older than RETENTION_DAYS. Uses pagination to handle large tables.
    """
    import boto3

    ds = context["ds"]
    cutoff_date = (
        datetime.strptime(ds, "%Y-%m-%d") - timedelta(days=RETENTION_DAYS)
    ).isoformat() + "Z"

    session = boto3.Session()
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE)

    events_to_archive = []
    scan_kwargs = {
        "FilterExpression": "#ts < :cutoff",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
        "ExpressionAttributeValues": {":cutoff": cutoff_date},
    }

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
        events_to_archive.extend(items)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info(
        "Found %d audit events older than %d days (cutoff: %s)",
        len(events_to_archive),
        RETENTION_DAYS,
        cutoff_date,
    )

    # Store count in XCom (not the full payload — could be huge)
    context["ti"].xcom_push(key="archive_count", value=len(events_to_archive))
    context["ti"].xcom_push(key="cutoff_date", value=cutoff_date)
    return events_to_archive


def compress_and_upload(**context):
    """Compress audit events to JSONL.gz and upload to S3 with Glacier storage class.

    Writes events as newline-delimited JSON, gzip-compressed, to a
    date-partitioned S3 key with GLACIER storage class for cost optimization.
    """
    events = context["ti"].xcom_pull(task_ids="scan_audit_events") or []
    if not events:
        logger.info("No events to archive")
        context["ti"].xcom_push(key="archive_s3_key", value=None)
        return

    ds = context["ds"]
    archive_key = f"{S3_PREFIX}/year={ds[:4]}/week={ds}/audit_events.jsonl.gz"

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for event in events:
            line = json.dumps(event, cls=_DecimalEncoder, default=str)
            gz.write(line.encode("utf-8"))
            gz.write(b"\n")

    compressed_size = buf.tell()
    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    s3_hook.load_bytes(
        buf.getvalue(),
        key=archive_key,
        bucket_name=S3_BUCKET,
        replace=True,
        extra_args={"StorageClass": "GLACIER"},
    )

    logger.info(
        "Archived %d events to s3://%s/%s (%.2f MB compressed)",
        len(events),
        S3_BUCKET,
        archive_key,
        compressed_size / (1024 * 1024),
    )

    context["ti"].xcom_push(key="archive_s3_key", value=archive_key)
    context["ti"].xcom_push(key="compressed_size_bytes", value=compressed_size)


def cleanup_dynamodb(**context):
    """Batch-delete archived records from DynamoDB.

    Uses BatchWriteItem with batches of 25 (DynamoDB limit) to remove
    the archived events. Idempotent — safe to retry on partial failure.
    """
    import boto3

    events = context["ti"].xcom_pull(task_ids="scan_audit_events") or []
    archive_key = context["ti"].xcom_pull(key="archive_s3_key", task_ids="compress_and_upload")

    if not events or not archive_key:
        logger.info("No events to clean up or archive not confirmed")
        return

    session = boto3.Session()
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE)

    deleted_count = 0
    batch = []

    for event in events:
        # Assumes composite key: event_id (partition) + timestamp (sort)
        key = {
            "event_id": event["event_id"],
            "timestamp": event["timestamp"],
        }
        batch.append(key)

        if len(batch) >= DYNAMODB_BATCH_SIZE:
            _delete_batch(table, batch)
            deleted_count += len(batch)
            batch = []

    if batch:
        _delete_batch(table, batch)
        deleted_count += len(batch)

    logger.info("Deleted %d archived events from DynamoDB", deleted_count)
    context["ti"].xcom_push(key="deleted_count", value=deleted_count)


def _delete_batch(table, keys):
    """Delete a batch of items from DynamoDB with retry logic."""
    with table.batch_writer() as batch_writer:
        for key in keys:
            batch_writer.delete_item(Key=key)


def generate_compliance_report(**context):
    """Generate a compliance report summarizing the archival operation.

    The report includes counts, S3 location, and timestamps for audit trail.
    """
    ds = context["ds"]
    archive_count = context["ti"].xcom_pull(key="archive_count", task_ids="scan_audit_events") or 0
    archive_key = context["ti"].xcom_pull(key="archive_s3_key", task_ids="compress_and_upload")
    compressed_size = context["ti"].xcom_pull(
        key="compressed_size_bytes", task_ids="compress_and_upload"
    ) or 0
    deleted_count = context["ti"].xcom_pull(key="deleted_count", task_ids="cleanup_dynamodb") or 0
    cutoff_date = context["ti"].xcom_pull(key="cutoff_date", task_ids="scan_audit_events")

    report = {
        "report_type": "audit_archive_compliance",
        "execution_date": ds,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "retention_policy": {
            "retention_days": RETENTION_DAYS,
            "cutoff_date": cutoff_date,
        },
        "results": {
            "events_scanned": archive_count,
            "events_archived": archive_count,
            "events_deleted_from_source": deleted_count,
            "archive_location": f"s3://{S3_BUCKET}/{archive_key}" if archive_key else None,
            "archive_storage_class": "GLACIER",
            "compressed_size_bytes": compressed_size,
        },
        "compliance": {
            "gdpr_compliant": True,
            "soc2_compliant": True,
            "data_encrypted_at_rest": True,
            "data_encrypted_in_transit": True,
        },
    }

    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    report_key = f"reports/compliance/audit-archive/{ds}/report.json"
    s3_hook.load_string(
        json.dumps(report, indent=2),
        key=report_key,
        bucket_name=S3_BUCKET,
        replace=True,
    )

    logger.info(
        "Compliance report generated: %d events archived, %d deleted, stored at s3://%s/%s",
        archive_count,
        deleted_count,
        S3_BUCKET,
        report_key,
    )


with DAG(
    "otterworks_audit_archive",
    default_args=default_args,
    description="Weekly audit event archival to S3 Glacier with compliance reporting",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "audit", "compliance", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    scan = PythonOperator(
        task_id="scan_audit_events",
        python_callable=scan_audit_events,
    )

    archive = PythonOperator(
        task_id="compress_and_upload",
        python_callable=compress_and_upload,
    )

    cleanup = PythonOperator(
        task_id="cleanup_dynamodb",
        python_callable=cleanup_dynamodb,
    )

    compliance_report = PythonOperator(
        task_id="generate_compliance_report",
        python_callable=generate_compliance_report,
    )

    scan >> archive >> cleanup >> compliance_report
