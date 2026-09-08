"""otterworks_analytics_etl — Airflow port of ``etl/scripts/analytics_daily.py``.

Drains the analytics SQS queue, scans the analytics-events DynamoDB table for
the report date, aggregates by user / document / file / hour, writes gzip JSON
partitions to the data lake, upserts ``analytics_daily_summary`` in PostgreSQL
and publishes a daily report.

    extract_from_sqs >> extract_from_dynamodb >> transform_events
        >> [load_to_data_lake, update_postgres_aggregates] >> generate_report
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.hooks.sqs import SqsHook
from airflow.providers.postgres.hooks.postgres import PostgresHook

from otterworks.analytics_transforms import (
    ANALYTICS_UPSERT_SQL,
    aggregate_events,
    analytics_report_key,
    build_analytics_report,
    encode_gzip_json,
    encode_gzip_jsonl,
    encode_json,
    hourly_breakdown_key,
    normalize_dynamodb_item,
    partition_key,
    summary_key,
    summary_upsert_params,
    top_users_key,
)
from otterworks.common import (
    AWS_CONN_ID,
    DEFAULT_ARGS,
    POSTGRES_CONN_ID,
    get_logger,
    get_variable,
    resolve_report_date,
    utc_now_iso,
)

log = get_logger(__name__)

SQS_BATCH_SIZE = 10
SQS_WAIT_TIME_SECONDS = 5
SQS_MAX_CONSECUTIVE_ERRORS = 3


def extract_from_sqs(queue_url: str, max_messages: int, sqs_hook: SqsHook) -> list[dict[str, Any]]:
    """Drain up to ``max_messages`` JSON events from the queue.

    Parsed messages are deleted in batches; malformed bodies are logged and left
    on the queue so the queue's redrive policy routes them to its dead-letter
    queue instead of silently dropping them.
    """
    client = sqs_hook.conn
    events: list[dict[str, Any]] = []
    processed = malformed = unacknowledged = consecutive_errors = 0

    while processed < max_messages:
        try:
            response = client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(SQS_BATCH_SIZE, max_messages - processed),
                WaitTimeSeconds=SQS_WAIT_TIME_SECONDS,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            log.warning(
                "sqs_receive_failed queue=%s consecutive=%d",
                queue_url,
                consecutive_errors,
                exc_info=True,
            )
            if consecutive_errors >= SQS_MAX_CONSECUTIVE_ERRORS:
                raise
            continue

        messages = response.get("Messages", [])
        if not messages:
            break

        parsed: dict[str, dict[str, Any]] = {}
        entries_to_delete = []
        for msg in messages:
            try:
                parsed[msg["MessageId"]] = json.loads(msg["Body"])
            except (ValueError, KeyError):
                malformed += 1
                log.warning(
                    "sqs_message_malformed queue=%s message_id=%s", queue_url, msg.get("MessageId")
                )
                continue
            entries_to_delete.append(
                {"Id": msg["MessageId"], "ReceiptHandle": msg["ReceiptHandle"]}
            )

        if entries_to_delete:
            deleted = client.delete_message_batch(QueueUrl=queue_url, Entries=entries_to_delete)
            # Only events whose delete was acknowledged count; the rest will be
            # redelivered by SQS and must not be aggregated twice.
            for failure in deleted.get("Failed", []):
                unacknowledged += 1
                parsed.pop(failure["Id"], None)
                log.warning(
                    "sqs_delete_failed queue=%s message_id=%s code=%s sender_fault=%s",
                    queue_url,
                    failure["Id"],
                    failure.get("Code"),
                    failure.get("SenderFault"),
                )
        events.extend(parsed.values())
        processed += len(messages)

    log.info(
        "sqs_extract_complete queue=%s messages=%d events=%d malformed=%d unacknowledged=%d",
        queue_url,
        processed,
        len(events),
        malformed,
        unacknowledged,
    )
    return events


def extract_from_dynamodb(
    table_name: str, report_date: str, dynamodb_hook: DynamoDBHook
) -> list[dict[str, Any]]:
    """Scan events whose ``event_date`` starts with the report date."""
    table = dynamodb_hook.conn.Table(table_name)
    events: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": "begins_with(event_date, :ds)",
        "ExpressionAttributeValues": {":ds": report_date},
    }
    pages = 0
    while True:
        response = table.scan(**scan_kwargs)
        pages += 1
        events.extend(normalize_dynamodb_item(item) for item in response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    log.info(
        "dynamodb_extract_complete table=%s report_date=%s pages=%d events=%d",
        table_name,
        report_date,
        pages,
        len(events),
    )
    return events


def load_to_data_lake(
    aggregates: dict[str, Any],
    *,
    bucket: str,
    analytics_prefix: str,
    report_date: str,
    s3_hook: S3Hook,
) -> list[str]:
    """Write summary / hourly / top-users partitions; returns the keys written."""
    uploads = (
        (summary_key(analytics_prefix, report_date), encode_gzip_json(aggregates["summary"])),
        (
            hourly_breakdown_key(analytics_prefix, report_date),
            encode_gzip_json(aggregates["hourly_breakdown"]),
        ),
        (
            top_users_key(analytics_prefix, report_date),
            encode_gzip_jsonl(aggregates["user_summaries"]),
        ),
    )
    for key, body in uploads:
        s3_hook.load_bytes(bytes_data=body, key=key, bucket_name=bucket, replace=True)
        log.info("data_lake_object_written dest=s3://%s/%s bytes=%d", bucket, key, len(body))
    log.info(
        "data_lake_load_complete dest=s3://%s/%s",
        bucket,
        partition_key(analytics_prefix, report_date),
    )
    return [key for key, _ in uploads]


@dag(
    dag_id="otterworks_analytics_etl",
    description="Daily analytics: SQS + DynamoDB -> S3 data lake + PostgreSQL (02:00 UTC)",
    schedule="0 2 * * *",
    start_date=datetime(2024, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"report_date": None},
    tags=["otterworks", "etl", "analytics"],
    doc_md=__doc__,
)
def otterworks_analytics_etl():
    @task(task_id="extract_from_sqs")
    def extract_from_sqs_task() -> list[dict[str, Any]]:
        return extract_from_sqs(
            queue_url=get_variable("otterworks_analytics_sqs_queue_url"),
            max_messages=int(get_variable("otterworks_analytics_sqs_max_messages")),
            sqs_hook=SqsHook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="extract_from_dynamodb")
    def extract_from_dynamodb_task(**context) -> list[dict[str, Any]]:
        return extract_from_dynamodb(
            table_name=get_variable("otterworks_analytics_events_table"),
            report_date=resolve_report_date(context),
            dynamodb_hook=DynamoDBHook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="transform_events")
    def transform_events_task(
        sqs_events: list[dict[str, Any]], dynamo_events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        events = sqs_events + dynamo_events
        log.info(
            "events_combined sqs=%d dynamodb=%d total=%d",
            len(sqs_events),
            len(dynamo_events),
            len(events),
        )
        if not events:
            raise AirflowSkipException("No events found for this run; nothing to aggregate")
        aggregates = aggregate_events(events)
        summary = aggregates["summary"]
        log.info(
            "aggregation_complete events=%d active_users=%d active_documents=%d active_files=%d",
            summary["total_events"],
            summary["active_users"],
            summary["active_documents"],
            summary["active_files"],
        )
        return aggregates

    @task(task_id="load_to_data_lake")
    def load_to_data_lake_task(aggregates: dict[str, Any], **context) -> list[str]:
        return load_to_data_lake(
            aggregates,
            bucket=get_variable("otterworks_data_lake_bucket"),
            analytics_prefix=get_variable("otterworks_analytics_prefix"),
            report_date=resolve_report_date(context),
            s3_hook=S3Hook(aws_conn_id=AWS_CONN_ID),
        )

    @task(task_id="update_postgres_aggregates")
    def update_postgres_aggregates_task(aggregates: dict[str, Any], **context) -> None:
        report_date = resolve_report_date(context)
        PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).run(
            ANALYTICS_UPSERT_SQL,
            parameters=summary_upsert_params(report_date, aggregates["summary"]),
        )
        log.info(
            "postgres_upsert_complete table=analytics_daily_summary report_date=%s", report_date
        )

    @task(task_id="generate_report")
    def generate_report_task(aggregates: dict[str, Any], **context) -> str:
        report_date = resolve_report_date(context)
        bucket = get_variable("otterworks_data_lake_bucket")
        report = build_analytics_report(
            report_date=report_date, generated_at=utc_now_iso(), aggregates=aggregates
        )
        key = analytics_report_key(report_date)
        S3Hook(aws_conn_id=AWS_CONN_ID).load_bytes(
            bytes_data=encode_json(report), key=key, bucket_name=bucket, replace=True
        )
        log.info(
            "analytics_report_written dest=s3://%s/%s events=%d active_users=%d",
            bucket,
            key,
            report["summary"]["total_events"],
            report["summary"]["active_users"],
        )
        return key

    sqs_events = extract_from_sqs_task()
    dynamo_events = extract_from_dynamodb_task()
    sqs_events >> dynamo_events
    aggregates = transform_events_task(sqs_events, dynamo_events)
    loads = [load_to_data_lake_task(aggregates), update_postgres_aggregates_task(aggregates)]
    loads >> generate_report_task(aggregates)


otterworks_analytics_etl()
