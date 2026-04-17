"""
OtterWorks Analytics ETL Pipeline

Daily pipeline that extracts usage events from SQS and DynamoDB,
transforms and aggregates them by user/document/file/time period,
then loads into S3 data lake (compressed JSON) and PostgreSQL aggregates.
"""

import gzip
import io
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.hooks.sqs import SqsHook
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

# Configuration defaults (used when Airflow Variables are not set)
_DEFAULT_SQS_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics"
_DEFAULT_DYNAMODB_TABLE = "otterworks-analytics-events"
_DEFAULT_S3_BUCKET = "otterworks-data-lake"
S3_PREFIX = "analytics/daily"
POSTGRES_CONN_ID = "otterworks_postgres"
AWS_CONN_ID = "aws_default"
MAX_SQS_MESSAGES = 10000
SQS_BATCH_SIZE = 10
SQS_WAIT_TIME = 5


def _get_sqs_queue_url():
    from airflow.models import Variable
    return Variable.get("otterworks_analytics_queue_url", default_var=_DEFAULT_SQS_QUEUE_URL)


def _get_dynamodb_table():
    from airflow.models import Variable
    return Variable.get("otterworks_analytics_table", default_var=_DEFAULT_DYNAMODB_TABLE)


def _get_s3_bucket():
    from airflow.models import Variable
    return Variable.get("otterworks_data_lake_bucket", default_var=_DEFAULT_S3_BUCKET)

default_args = {
    "owner": "otterworks-data",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def extract_from_sqs(**context):
    """Poll SQS analytics queue for usage events.

    Reads up to MAX_SQS_MESSAGES from the analytics queue, deletes
    processed messages, and pushes the raw event list via XCom.
    """
    sqs_hook = SqsHook(aws_conn_id=AWS_CONN_ID)
    sqs_client = sqs_hook.get_conn()
    queue_url = _get_sqs_queue_url()

    all_events = []
    messages_processed = 0

    while messages_processed < MAX_SQS_MESSAGES:
        response = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=SQS_BATCH_SIZE,
            WaitTimeSeconds=SQS_WAIT_TIME,
            AttributeNames=["All"],
            MessageAttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        if not messages:
            logger.info("No more messages in SQS queue after %d messages", messages_processed)
            break

        entries_to_delete = []
        for msg in messages:
            try:
                event = json.loads(msg["Body"])
                all_events.append(event)
                entries_to_delete.append(
                    {"Id": msg["MessageId"], "ReceiptHandle": msg["ReceiptHandle"]}
                )
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Skipping malformed SQS message %s: %s", msg.get("MessageId"), exc)

        if entries_to_delete:
            sqs_client.delete_message_batch(QueueUrl=queue_url, Entries=entries_to_delete)

        messages_processed += len(messages)

    logger.info("Extracted %d events from SQS", len(all_events))
    context["ti"].xcom_push(key="sqs_event_count", value=len(all_events))
    return all_events


def extract_from_dynamodb(**context):
    """Read analytics events from DynamoDB for the execution date.

    Queries the DynamoDB analytics table using a date-based partition key
    to retrieve all events for the given execution date.
    """
    ds = context["ds"]
    dynamodb_hook = DynamoDBHook(aws_conn_id=AWS_CONN_ID, table_name=_get_dynamodb_table())
    table = dynamodb_hook.get_conn()

    all_items = []
    scan_kwargs = {
        "FilterExpression": "begins_with(event_date, :ds)",
        "ExpressionAttributeValues": {":ds": ds},
    }

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
        all_items.extend(items)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info("Extracted %d events from DynamoDB for date %s", len(all_items), ds)
    context["ti"].xcom_push(key="dynamodb_event_count", value=len(all_items))
    return all_items


def transform_events(**context):
    """Transform and aggregate raw events into analytics records.

    Aggregates events by:
      - User activity (active users, actions per user)
      - Document metrics (creates, edits, comments)
      - File metrics (uploads, downloads, shares, deletes)
      - Time-bucketed hourly breakdowns
    """
    ds = context["ds"]
    sqs_events = context["ti"].xcom_pull(task_ids="extract_from_sqs") or []
    dynamo_events = context["ti"].xcom_pull(task_ids="extract_from_dynamodb") or []

    all_events = sqs_events + dynamo_events
    logger.info("Transforming %d total events for %s", len(all_events), ds)

    aggregated = _aggregate_events(all_events, ds)

    context["ti"].xcom_push(key="aggregated", value=aggregated)
    context["ti"].xcom_push(key="total_events", value=len(all_events))
    return aggregated


def _aggregate_events(events, ds):
    """Core aggregation logic - separated for testability.

    Args:
        events: List of raw event dicts.
        ds: Execution date string (YYYY-MM-DD).

    Returns:
        Dict with aggregated metrics keyed by category.
    """
    user_actions = defaultdict(lambda: defaultdict(int))
    document_metrics = defaultdict(int)
    file_metrics = defaultdict(int)
    hourly_buckets = defaultdict(lambda: defaultdict(int))
    active_users = set()
    active_documents = set()
    active_files = set()

    for event in events:
        event_type = event.get("eventType", event.get("event_type", ""))
        user_id = (
            event.get("ownerId")
            or event.get("editedBy")
            or event.get("authorId")
            or event.get("deletedBy")
            or event.get("userId")
            or "unknown"
        )
        timestamp_str = event.get("timestamp", "")

        active_users.add(user_id)
        user_actions[user_id][event_type] += 1

        # Parse hour bucket
        hour = "00"
        if timestamp_str:
            try:
                ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                hour = f"{ts.hour:02d}"
            except (ValueError, AttributeError):
                pass
        hourly_buckets[hour][event_type] += 1

        # Document metrics
        if event_type == "document_created":
            document_metrics["created"] += 1
            doc_id = event.get("documentId", "")
            if doc_id:
                active_documents.add(doc_id)
        elif event_type == "document_edited":
            document_metrics["edited"] += 1
            doc_id = event.get("documentId", "")
            if doc_id:
                active_documents.add(doc_id)
        elif event_type == "comment_added":
            document_metrics["comments"] += 1

        # File metrics
        elif event_type == "file_uploaded":
            file_metrics["uploaded"] += 1
            file_metrics["bytes_uploaded"] += event.get("sizeBytes", 0)
            file_id = event.get("fileId", "")
            if file_id:
                active_files.add(file_id)
        elif event_type == "file_shared":
            file_metrics["shared"] += 1
            file_id = event.get("fileId", "")
            if file_id:
                active_files.add(file_id)
        elif event_type == "file_deleted":
            file_metrics["deleted"] += 1
            file_id = event.get("fileId", "")
            if file_id:
                active_files.add(file_id)

    # Build per-user summaries (top 100 most active for XCom size safety)
    user_summaries = []
    for uid, actions in sorted(
        user_actions.items(), key=lambda x: sum(x[1].values()), reverse=True
    )[:100]:
        user_summaries.append(
            {"user_id": uid, "actions": dict(actions), "total": sum(actions.values())}
        )

    return {
        "date": ds,
        "summary": {
            "active_users": len(active_users),
            "active_documents": len(active_documents),
            "active_files": len(active_files),
            "total_events": len(events),
            "documents_created": document_metrics.get("created", 0),
            "documents_edited": document_metrics.get("edited", 0),
            "comments_added": document_metrics.get("comments", 0),
            "files_uploaded": file_metrics.get("uploaded", 0),
            "files_shared": file_metrics.get("shared", 0),
            "files_deleted": file_metrics.get("deleted", 0),
            "bytes_uploaded": file_metrics.get("bytes_uploaded", 0),
        },
        "document_metrics": dict(document_metrics),
        "file_metrics": dict(file_metrics),
        "hourly_breakdown": {h: dict(v) for h, v in sorted(hourly_buckets.items())},
        "top_users": user_summaries,
    }


def load_to_data_lake(**context):
    """Load aggregated analytics to S3 data lake as compressed JSON.

    Writes date-partitioned files to S3 for downstream Spark/Athena queries.
    """
    ds = context["ds"]
    aggregated = context["ti"].xcom_pull(key="aggregated", task_ids="transform_events")
    if not aggregated:
        logger.warning("No aggregated data to load for %s", ds)
        return

    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    bucket = _get_s3_bucket()
    partition_key = f"{S3_PREFIX}/year={ds[:4]}/month={ds[5:7]}/day={ds[8:10]}"

    # Write summary
    summary_key = f"{partition_key}/summary.json.gz"
    summary_bytes = gzip.compress(
        json.dumps(aggregated["summary"], indent=2).encode("utf-8")
    )
    s3_hook.load_bytes(
        summary_bytes,
        key=summary_key,
        bucket_name=bucket,
        replace=True,
    )

    # Write hourly breakdown
    hourly_key = f"{partition_key}/hourly_breakdown.json.gz"
    hourly_bytes = gzip.compress(
        json.dumps(aggregated["hourly_breakdown"], indent=2).encode("utf-8")
    )
    s3_hook.load_bytes(
        hourly_bytes,
        key=hourly_key,
        bucket_name=bucket,
        replace=True,
    )

    # Write top users as JSONL
    users_key = f"{partition_key}/top_users.jsonl.gz"
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for user in aggregated.get("top_users", []):
            gz.write(json.dumps(user).encode("utf-8"))
            gz.write(b"\n")
    s3_hook.load_bytes(
        buf.getvalue(),
        key=users_key,
        bucket_name=bucket,
        replace=True,
    )

    logger.info("Loaded analytics data to s3://%s/%s", bucket, partition_key)
    context["ti"].xcom_push(key="s3_partition", value=partition_key)


def update_postgres_aggregates(**context):
    """Upsert daily aggregate metrics into PostgreSQL for fast dashboard queries."""
    ds = context["ds"]
    aggregated = context["ti"].xcom_pull(key="aggregated", task_ids="transform_events")
    if not aggregated:
        logger.warning("No aggregated data to update for %s", ds)
        return

    summary = aggregated.get("summary", {})
    pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)

    upsert_sql = """
        INSERT INTO analytics_daily_summary (
            report_date, active_users, active_documents, active_files,
            total_events, documents_created, documents_edited,
            comments_added, files_uploaded, files_shared,
            files_deleted, bytes_uploaded, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
        )
        ON CONFLICT (report_date) DO UPDATE SET
            active_users = EXCLUDED.active_users,
            active_documents = EXCLUDED.active_documents,
            active_files = EXCLUDED.active_files,
            total_events = EXCLUDED.total_events,
            documents_created = EXCLUDED.documents_created,
            documents_edited = EXCLUDED.documents_edited,
            comments_added = EXCLUDED.comments_added,
            files_uploaded = EXCLUDED.files_uploaded,
            files_shared = EXCLUDED.files_shared,
            files_deleted = EXCLUDED.files_deleted,
            bytes_uploaded = EXCLUDED.bytes_uploaded,
            updated_at = NOW();
    """

    pg_hook.run(
        upsert_sql,
        parameters=(
            ds,
            summary.get("active_users", 0),
            summary.get("active_documents", 0),
            summary.get("active_files", 0),
            summary.get("total_events", 0),
            summary.get("documents_created", 0),
            summary.get("documents_edited", 0),
            summary.get("comments_added", 0),
            summary.get("files_uploaded", 0),
            summary.get("files_shared", 0),
            summary.get("files_deleted", 0),
            summary.get("bytes_uploaded", 0),
        ),
    )

    logger.info("Updated PostgreSQL daily aggregates for %s", ds)


def generate_report(**context):
    """Generate daily analytics summary report and push to S3."""
    ds = context["ds"]
    aggregated = context["ti"].xcom_pull(key="aggregated", task_ids="transform_events")
    if not aggregated:
        logger.warning("No data for report generation on %s", ds)
        return

    summary = aggregated.get("summary", {})
    report = _build_daily_report(ds, summary, aggregated)

    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    report_key = f"reports/analytics/daily/{ds}/report.json"
    s3_hook.load_string(
        json.dumps(report, indent=2),
        key=report_key,
        bucket_name=_get_s3_bucket(),
        replace=True,
    )

    logger.info(
        "Generated daily analytics report for %s: %d events, %d active users",
        ds,
        summary.get("total_events", 0),
        summary.get("active_users", 0),
    )


def _build_daily_report(ds, summary, aggregated):
    """Build the daily report dict - separated for testability."""
    return {
        "report_type": "daily_analytics",
        "report_date": ds,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": summary,
        "highlights": {
            "peak_hour": _find_peak_hour(aggregated.get("hourly_breakdown", {})),
            "most_active_users": [
                u["user_id"] for u in aggregated.get("top_users", [])[:5]
            ],
        },
        "document_metrics": aggregated.get("document_metrics", {}),
        "file_metrics": aggregated.get("file_metrics", {}),
    }


def _find_peak_hour(hourly_breakdown):
    """Find the hour with the most total events."""
    if not hourly_breakdown:
        return None
    peak = max(hourly_breakdown.items(), key=lambda x: sum(x[1].values()))
    return {"hour": peak[0], "event_count": sum(peak[1].values())}


with DAG(
    "otterworks_analytics_etl",
    default_args=default_args,
    description="Daily analytics ETL: SQS + DynamoDB -> S3 data lake + PostgreSQL aggregates",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "analytics", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    extract_sqs = PythonOperator(
        task_id="extract_from_sqs",
        python_callable=extract_from_sqs,
    )

    extract_dynamo = PythonOperator(
        task_id="extract_from_dynamodb",
        python_callable=extract_from_dynamodb,
    )

    transform = PythonOperator(
        task_id="transform_events",
        python_callable=transform_events,
    )

    load_s3 = PythonOperator(
        task_id="load_to_data_lake",
        python_callable=load_to_data_lake,
    )

    update_pg = PythonOperator(
        task_id="update_postgres_aggregates",
        python_callable=update_postgres_aggregates,
    )

    report = PythonOperator(
        task_id="generate_report",
        python_callable=generate_report,
    )

    # Extract from both sources in parallel, then transform, then load + report
    [extract_sqs, extract_dynamo] >> transform >> [load_s3, update_pg] >> report
