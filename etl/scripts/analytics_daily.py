#!/usr/bin/env python3
# analytics_daily.py - Daily analytics aggregation pipeline
# Originally Python 2.7, minimally ported to Python 3 in 2021
# Pulls events from SQS + DynamoDB, aggregates, loads to S3 and PostgreSQL
#
# Owner: Jake (data-team@otterworks.dev) -- Jake left mid-2020
# TODO ETL-078: Refactor this into proper modules (deferred Q4 2019)
# TODO ETL-142: Move credentials to secrets manager (deferred Q3 2020)
# TODO ETL-201: Add unit tests (never prioritized)

import configparser
import gzip
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pandas as pd
import psycopg2

# TODO ETL-089: Make queue URL configurable per environment (2019-11-15)
SQS_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics"
DYNAMODB_TABLE_NAME = "otterworks-analytics-events"
MAX_MESSAGES = 10000  # hardcoded limit
SQS_BATCH_SIZE = 10
MAX_CONSECUTIVE_ERRORS = 3
USER_ID_FIELDS = ["ownerId", "editedBy", "authorId", "deletedBy", "userId"]
TOP_USERS_LIMIT = 100

UPSERT_SQL = """
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


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_config():
    config = configparser.ConfigParser()
    config.read("/opt/etl/config.ini")
    return config


def aws_credentials(config):
    return {
        "aws_access_key_id": config.get("aws", "access_key"),
        "aws_secret_access_key": config.get("aws", "secret_key"),
        "region_name": config.get("aws", "region"),
    }


def parse_messages(messages):
    """Decode SQS message bodies, returning the events and their delete entries."""
    events = []
    entries_to_delete = []

    for msg in messages:
        try:
            event = json.loads(msg["Body"])
            events.append(event)
            entries_to_delete.append(
                {"Id": msg["MessageId"], "ReceiptHandle": msg["ReceiptHandle"]}
            )
        except:
            # TODO ETL-103: Add dead-letter queue for malformed messages (2020-01-08)
            pass

    return events, entries_to_delete


def extract_sqs_events(sqs_client):
    all_sqs_events = []
    messages_processed = 0
    consecutive_errors = 0

    print("[%s] Polling SQS queue: %s" % (now_str(), SQS_QUEUE_URL))

    while messages_processed < MAX_MESSAGES:
        try:
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=SQS_BATCH_SIZE,
                WaitTimeSeconds=5,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            consecutive_errors = 0
        except:
            # TODO ETL-103: Add dead-letter queue for failed SQS calls (2020-01-08)
            consecutive_errors += 1
            print("[%s] WARNING: SQS receive failed (%d consecutive)" % (now_str(), consecutive_errors))
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print("[%s] ERROR: Too many SQS failures, giving up" % now_str())
                break
            continue

        messages = response.get("Messages", [])
        if not messages:
            print("[%s] No more messages after %d processed" % (now_str(), messages_processed))
            break

        events, entries_to_delete = parse_messages(messages)
        all_sqs_events.extend(events)

        if entries_to_delete:
            sqs_client.delete_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=entries_to_delete)

        messages_processed += len(messages)

    return all_sqs_events


def normalize_decimals(item):
    for k, v in item.items():
        if isinstance(v, Decimal):
            item[k] = int(v) if v == int(v) else float(v)


def extract_dynamo_events(dynamodb, ds):
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)

    all_dynamo_events = []
    scan_kwargs = {
        "FilterExpression": "begins_with(event_date, :ds)",
        "ExpressionAttributeValues": {":ds": ds},
    }

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
        # convert Decimals to native types for json serialization later
        for item in items:
            normalize_decimals(item)
        all_dynamo_events.extend(items)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    return all_dynamo_events


def parse_hour(ts):
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return "%02d" % dt.hour
    except:
        pass
    return "00"


def prepare_dataframe(all_events):
    """Build the events frame with normalized event type, user ID and hour columns."""
    # TODO ETL-155: This pandas approach is slow for large datasets, consider PySpark (2020-03-22)
    df = pd.DataFrame(all_events)

    # Normalize event type field name
    if "event_type" in df.columns and "eventType" not in df.columns:
        df["eventType"] = df["event_type"]
    if "eventType" not in df.columns:
        df["eventType"] = "unknown"

    # Resolve user ID from whichever field is populated
    df["resolved_user_id"] = "unknown"
    for col in USER_ID_FIELDS:
        if col in df.columns:
            mask = (df["resolved_user_id"] == "unknown") & df[col].notna() & (df[col] != "")
            df.loc[mask, "resolved_user_id"] = df.loc[mask, col]

    # Parse timestamps for hourly bucketing
    df["hour"] = "00"
    if "timestamp" in df.columns:
        df["hour"] = df["timestamp"].apply(parse_hour)

    return df


def aggregate_user_actions(df):
    """Return the active user set and the top user summaries by total actions."""
    active_users = set(df["resolved_user_id"].unique()) - {"unknown"}

    user_action_counts = {}
    for _, row in df.iterrows():
        uid = row["resolved_user_id"]
        etype = row.get("eventType", "unknown")
        if uid not in user_action_counts:
            user_action_counts[uid] = {}
        if etype not in user_action_counts[uid]:
            user_action_counts[uid][etype] = 0
        user_action_counts[uid][etype] += 1

    user_summaries = []
    for uid, actions in user_action_counts.items():
        total = sum(actions.values())
        user_summaries.append({"user_id": uid, "actions": actions, "total": total})
    user_summaries.sort(key=lambda x: x["total"], reverse=True)

    return active_users, user_summaries[:TOP_USERS_LIMIT]


def compute_document_metrics(df):
    documents_created = 0
    documents_edited = 0
    comments_added = 0
    active_documents = set()

    if "eventType" in df.columns:
        doc_created = df[df["eventType"] == "document_created"]
        documents_created = len(doc_created)
        if "documentId" in df.columns:
            active_documents.update(doc_created["documentId"].dropna().unique())

        doc_edited = df[df["eventType"] == "document_edited"]
        documents_edited = len(doc_edited)
        if "documentId" in df.columns:
            active_documents.update(doc_edited["documentId"].dropna().unique())

        doc_comments = df[df["eventType"] == "comment_added"]
        comments_added = len(doc_comments)

    metrics = {
        "created": documents_created,
        "edited": documents_edited,
        "comments": comments_added,
    }
    return metrics, active_documents


def compute_file_metrics(df):
    files_uploaded = 0
    files_shared = 0
    files_deleted = 0
    bytes_uploaded = 0
    active_files = set()

    if "eventType" in df.columns:
        uploaded = df[df["eventType"] == "file_uploaded"]
        files_uploaded = len(uploaded)
        if "sizeBytes" in df.columns:
            bytes_uploaded = int(uploaded["sizeBytes"].fillna(0).sum())
        if "fileId" in df.columns:
            active_files.update(uploaded["fileId"].dropna().unique())

        shared = df[df["eventType"] == "file_shared"]
        files_shared = len(shared)
        if "fileId" in df.columns:
            active_files.update(shared["fileId"].dropna().unique())

        deleted = df[df["eventType"] == "file_deleted"]
        files_deleted = len(deleted)
        if "fileId" in df.columns:
            active_files.update(deleted["fileId"].dropna().unique())

    metrics = {
        "uploaded": files_uploaded,
        "shared": files_shared,
        "deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }
    return metrics, active_files


def compute_hourly_breakdown(df):
    hourly_breakdown = {}
    for _, row in df.iterrows():
        h = row.get("hour", "00")
        etype = row.get("eventType", "unknown")
        if h not in hourly_breakdown:
            hourly_breakdown[h] = {}
        if etype not in hourly_breakdown[h]:
            hourly_breakdown[h][etype] = 0
        hourly_breakdown[h][etype] += 1

    # Sort hourly breakdown
    return dict(sorted(hourly_breakdown.items()))


def build_summary(all_events, active_users, active_documents, active_files,
                  document_metrics, file_metrics):
    return {
        "active_users": len(active_users),
        "active_documents": len(active_documents),
        "active_files": len(active_files),
        "total_events": len(all_events),
        "documents_created": document_metrics["created"],
        "documents_edited": document_metrics["edited"],
        "comments_added": document_metrics["comments"],
        "files_uploaded": file_metrics["uploaded"],
        "files_shared": file_metrics["shared"],
        "files_deleted": file_metrics["deleted"],
        "bytes_uploaded": file_metrics["bytes_uploaded"],
    }


def load_to_data_lake(s3_client, data_lake_bucket, partition_key, summary,
                      hourly_breakdown, user_summaries):
    # Write summary
    summary_key = "%s/summary.json.gz" % partition_key
    summary_bytes = gzip.compress(json.dumps(summary, indent=2).encode("utf-8"))
    s3_client.put_object(
        Bucket=data_lake_bucket,
        Key=summary_key,
        Body=summary_bytes,
    )
    print("[%s] Uploaded summary to s3://%s/%s" % (now_str(), data_lake_bucket, summary_key))

    # Write hourly breakdown
    hourly_key = "%s/hourly_breakdown.json.gz" % partition_key
    hourly_bytes = gzip.compress(json.dumps(hourly_breakdown, indent=2).encode("utf-8"))
    s3_client.put_object(
        Bucket=data_lake_bucket,
        Key=hourly_key,
        Body=hourly_bytes,
    )

    # Write top users as JSONL
    users_key = "%s/top_users.jsonl.gz" % partition_key
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for user in user_summaries:
            gz.write(json.dumps(user).encode("utf-8"))
            gz.write(b"\n")
    s3_client.put_object(
        Bucket=data_lake_bucket,
        Key=users_key,
        Body=buf.getvalue(),
    )


def upsert_daily_summary(config, ds, summary):
    db_host = config.get("database", "host")
    db_port = config.getint("database", "port")
    db_name = config.get("database", "database")

    print("[%s] Connecting to PostgreSQL at %s:%d/%s" % (now_str(), db_host, db_port, db_name))

    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=config.get("database", "user"),
            password=config.get("database", "password"),
        )
        cursor = conn.cursor()
        cursor.execute(UPSERT_SQL, (
            ds,
            summary["active_users"],
            summary["active_documents"],
            summary["active_files"],
            summary["total_events"],
            summary["documents_created"],
            summary["documents_edited"],
            summary["comments_added"],
            summary["files_uploaded"],
            summary["files_shared"],
            summary["files_deleted"],
            summary["bytes_uploaded"],
        ))
        conn.commit()
        print("[%s] Updated PostgreSQL daily aggregates for %s" % (now_str(), ds))
    except Exception as e:
        print("[%s] ERROR: PostgreSQL update failed: %s" % (now_str(), str(e)))
        if conn:
            conn.rollback()
        # don't exit -- still try to generate report
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def build_report(ds, summary, hourly_breakdown, user_summaries,
                 document_metrics, file_metrics):
    # Find peak hour
    peak_hour = None
    if hourly_breakdown:
        peak = max(hourly_breakdown.items(), key=lambda x: sum(x[1].values()))
        peak_hour = {"hour": peak[0], "event_count": sum(peak[1].values())}

    return {
        "report_type": "daily_analytics",
        "report_date": ds,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": summary,
        "highlights": {
            "peak_hour": peak_hour,
            "most_active_users": [u["user_id"] for u in user_summaries[:5]],
        },
        "document_metrics": document_metrics,
        "file_metrics": file_metrics,
    }


def main():
    print("[%s] analytics_daily.py starting..." % now_str())

    # ---- Load config ----
    config = load_config()
    aws_creds = aws_credentials(config)

    data_lake_bucket = config.get("s3", "data_lake_bucket")
    analytics_prefix = config.get("s3", "analytics_prefix")

    # today's date for partitioning
    ds = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    print("[%s] Processing analytics for date: %s" % (now_str(), ds))

    # ---- Extract from SQS ----
    all_sqs_events = extract_sqs_events(boto3.client("sqs", **aws_creds))
    print("[%s] Extracted %d events from SQS" % (now_str(), len(all_sqs_events)))

    # ---- Extract from DynamoDB ----
    all_dynamo_events = extract_dynamo_events(boto3.resource("dynamodb", **aws_creds), ds)
    print("[%s] Extracted %d events from DynamoDB for %s" % (now_str(), len(all_dynamo_events), ds))

    # ---- Combine all events ----
    all_events = all_sqs_events + all_dynamo_events
    print("[%s] Total events to process: %d" % (now_str(), len(all_events)))

    if len(all_events) == 0:
        print("[%s] WARNING: No events found, exiting" % now_str())
        sys.exit(0)

    # ---- Transform and aggregate using pandas ----
    df = prepare_dataframe(all_events)

    active_users, user_summaries = aggregate_user_actions(df)
    document_metrics, active_documents = compute_document_metrics(df)
    file_metrics, active_files = compute_file_metrics(df)
    hourly_breakdown = compute_hourly_breakdown(df)

    # ---- Build aggregated result ----
    summary = build_summary(
        all_events, active_users, active_documents, active_files,
        document_metrics, file_metrics,
    )

    print("[%s] Aggregation complete: %d events, %d active users, %d documents, %d files" % (
        now_str(),
        len(all_events),
        len(active_users),
        len(active_documents),
        len(active_files),
    ))

    # ---- Load to S3 data lake ----
    s3_client = boto3.client("s3", **aws_creds)

    partition_key = "%s/year=%s/month=%s/day=%s" % (analytics_prefix, ds[:4], ds[5:7], ds[8:10])

    load_to_data_lake(
        s3_client, data_lake_bucket, partition_key,
        summary, hourly_breakdown, user_summaries,
    )

    print("[%s] Loaded analytics data to s3://%s/%s" % (now_str(), data_lake_bucket, partition_key))

    # ---- Upsert PostgreSQL aggregates ----
    upsert_daily_summary(config, ds, summary)

    # ---- Generate daily report ----
    report = build_report(
        ds, summary, hourly_breakdown, user_summaries,
        document_metrics, file_metrics,
    )

    report_key = "reports/analytics/daily/%s/report.json" % ds
    s3_client_report = boto3.client("s3", **aws_creds)
    s3_client_report.put_object(
        Bucket=data_lake_bucket,
        Key=report_key,
        Body=json.dumps(report, indent=2).encode("utf-8"),
    )

    print("[%s] Generated daily analytics report: %d events, %d active users" % (
        now_str(),
        summary["total_events"],
        summary["active_users"],
    ))
    print("[%s] analytics_daily.py completed successfully" % now_str())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[%s] FATAL: %s" % (now_str(), str(e)))
        sys.exit(1)
