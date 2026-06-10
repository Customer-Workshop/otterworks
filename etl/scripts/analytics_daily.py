#!/usr/bin/env python3
# analytics_daily.py - Daily analytics aggregation pipeline
# Originally Python 2.7, minimally ported to Python 3 in 2021
# Pulls events from SQS + DynamoDB, aggregates, loads to S3 and PostgreSQL

import configparser
import gzip
import io
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import pandas as pd
import psycopg2

_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_hour(ts):
    """Extract zero-padded hour string from a timestamp value."""
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return "%02d" % dt.hour
    except (ValueError, TypeError):
        pass
    return "00"


def _poll_sqs_events(sqs_client, queue_url, max_messages, batch_size):
    """Poll SQS queue and return collected events."""
    all_events = []
    messages_processed = 0
    consecutive_errors = 0

    print("[%s] Polling SQS queue: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), queue_url))

    while messages_processed < max_messages:
        try:
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=batch_size,
                WaitTimeSeconds=5,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            print("[%s] WARNING: SQS receive failed (%d consecutive)" % (datetime.now().strftime(_TIMESTAMP_FMT), consecutive_errors))
            if consecutive_errors >= 3:
                print("[%s] ERROR: Too many SQS failures, giving up" % datetime.now().strftime(_TIMESTAMP_FMT))
                break
            continue

        messages = response.get("Messages", [])
        if not messages:
            print("[%s] No more messages after %d processed" % (datetime.now().strftime(_TIMESTAMP_FMT), messages_processed))
            break

        entries_to_delete = []
        for msg in messages:
            try:
                event = json.loads(msg["Body"])
                all_events.append(event)
                entries_to_delete.append(
                    {"Id": msg["MessageId"], "ReceiptHandle": msg["ReceiptHandle"]}
                )
            except (json.JSONDecodeError, KeyError):
                pass

        if entries_to_delete:
            sqs_client.delete_message_batch(QueueUrl=queue_url, Entries=entries_to_delete)

        messages_processed += len(messages)

    print("[%s] Extracted %d events from SQS" % (datetime.now().strftime(_TIMESTAMP_FMT), len(all_events)))
    return all_events


def _scan_dynamo_events(table, ds):
    """Scan DynamoDB for events matching the given date."""
    all_events = []
    scan_kwargs = {
        "FilterExpression": "begins_with(event_date, :ds)",
        "ExpressionAttributeValues": {":ds": ds},
    }

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
        for item in items:
            for k, v in item.items():
                if isinstance(v, Decimal):
                    item[k] = int(v) if v == int(v) else float(v)
        all_events.extend(items)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    print("[%s] Extracted %d events from DynamoDB for %s" % (datetime.now().strftime(_TIMESTAMP_FMT), len(all_events), ds))
    return all_events


def main():
    print("[%s] analytics_daily.py starting..." % datetime.now().strftime(_TIMESTAMP_FMT))

    # ---- Load config ----
    config = configparser.ConfigParser()
    config.read("/opt/etl/config.ini")

    aws_access_key = config.get("aws", "access_key")
    aws_secret_key = config.get("aws", "secret_key")
    aws_region = config.get("aws", "region")
    expected_account_id = config.get("aws", "account_id", fallback=os.environ.get("AWS_ACCOUNT_ID", ""))
    bucket_owner_kwargs = {"ExpectedBucketOwner": expected_account_id} if expected_account_id else {}

    db_host = config.get("database", "host")
    db_port = config.getint("database", "port")
    db_name = config.get("database", "database")
    db_user = config.get("database", "user")
    db_password = config.get("database", "password")

    data_lake_bucket = config.get("s3", "data_lake_bucket")
    analytics_prefix = config.get("s3", "analytics_prefix")

    # today's date for partitioning
    ds = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    print("[%s] Processing analytics for date: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), ds))

    # ---- Extract from SQS ----
    sqs_queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics"
    sqs_client = boto3.client(
        "sqs",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )

    max_messages = 10000  # hardcoded limit
    batch_size = 10

    all_sqs_events = _poll_sqs_events(sqs_client, sqs_queue_url, max_messages, batch_size)

    # ---- Extract from DynamoDB ----
    dynamodb_table_name = "otterworks-analytics-events"
    dynamodb = boto3.resource(
        "dynamodb",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    table = dynamodb.Table(dynamodb_table_name)

    all_dynamo_events = _scan_dynamo_events(table, ds)

    # ---- Combine all events ----
    all_events = all_sqs_events + all_dynamo_events
    print("[%s] Total events to process: %d" % (datetime.now().strftime(_TIMESTAMP_FMT), len(all_events)))

    if len(all_events) == 0:
        print("[%s] WARNING: No events found, exiting" % datetime.now().strftime(_TIMESTAMP_FMT))
        sys.exit(0)

    # ---- Transform and aggregate using pandas ----
    df = pd.DataFrame(all_events)

    # Normalize event type field name
    if "event_type" in df.columns and "eventType" not in df.columns:
        df["eventType"] = df["event_type"]
    if "eventType" not in df.columns:
        df["eventType"] = "unknown"

    # Resolve user ID from whichever field is populated
    df["resolved_user_id"] = "unknown"
    for col in ["ownerId", "editedBy", "authorId", "deletedBy", "userId"]:
        if col in df.columns:
            mask = (df["resolved_user_id"] == "unknown") & df[col].notna() & (df[col] != "")
            df.loc[mask, "resolved_user_id"] = df.loc[mask, col]

    # Parse timestamps for hourly bucketing
    df["hour"] = "00"
    if "timestamp" in df.columns:
        df["hour"] = df["timestamp"].apply(_parse_hour)

    # ---- Aggregate user actions ----
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

    # Build top users list (top 100 by total actions)
    user_summaries = []
    for uid, actions in user_action_counts.items():
        total = sum(actions.values())
        user_summaries.append({"user_id": uid, "actions": actions, "total": total})
    user_summaries.sort(key=lambda x: x["total"], reverse=True)
    user_summaries = user_summaries[:100]

    # ---- Document metrics ----
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

    # ---- File metrics ----
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

    # ---- Hourly breakdown ----
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
    hourly_breakdown = dict(sorted(hourly_breakdown.items()))

    # ---- Build aggregated result ----
    document_metrics = {
        "created": documents_created,
        "edited": documents_edited,
        "comments": comments_added,
    }
    file_metrics = {
        "uploaded": files_uploaded,
        "shared": files_shared,
        "deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }

    summary = {
        "active_users": len(active_users),
        "active_documents": len(active_documents),
        "active_files": len(active_files),
        "total_events": len(all_events),
        "documents_created": documents_created,
        "documents_edited": documents_edited,
        "comments_added": comments_added,
        "files_uploaded": files_uploaded,
        "files_shared": files_shared,
        "files_deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }

    print("[%s] Aggregation complete: %d events, %d active users, %d documents, %d files" % (
        datetime.now().strftime(_TIMESTAMP_FMT),
        len(all_events),
        len(active_users),
        len(active_documents),
        len(active_files),
    ))

    # ---- Load to S3 data lake ----
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )

    partition_key = "%s/year=%s/month=%s/day=%s" % (analytics_prefix, ds[:4], ds[5:7], ds[8:10])

    # Write summary
    summary_key = "%s/summary.json.gz" % partition_key
    summary_bytes = gzip.compress(json.dumps(summary, indent=2).encode("utf-8"))
    s3_client.put_object(
        Bucket=data_lake_bucket,
        Key=summary_key,
        Body=summary_bytes,
        **bucket_owner_kwargs,
    )
    print("[%s] Uploaded summary to s3://%s/%s" % (datetime.now().strftime(_TIMESTAMP_FMT), data_lake_bucket, summary_key))

    # Write hourly breakdown
    hourly_key = "%s/hourly_breakdown.json.gz" % partition_key
    hourly_bytes = gzip.compress(json.dumps(hourly_breakdown, indent=2).encode("utf-8"))
    s3_client.put_object(
        Bucket=data_lake_bucket,
        Key=hourly_key,
        Body=hourly_bytes,
        **bucket_owner_kwargs,
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
        **bucket_owner_kwargs,
    )

    print("[%s] Loaded analytics data to s3://%s/%s" % (datetime.now().strftime(_TIMESTAMP_FMT), data_lake_bucket, partition_key))

    # ---- Upsert PostgreSQL aggregates ----
    print("[%s] Connecting to PostgreSQL at %s:%d/%s" % (datetime.now().strftime(_TIMESTAMP_FMT), db_host, db_port, db_name))

    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
        )
        cursor = conn.cursor()

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

        cursor.execute(upsert_sql, (
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
        print("[%s] Updated PostgreSQL daily aggregates for %s" % (datetime.now().strftime(_TIMESTAMP_FMT), ds))
    except Exception as e:
        print("[%s] ERROR: PostgreSQL update failed: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), str(e)))
        if conn:
            conn.rollback()
        # don't exit -- still try to generate report
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # ---- Generate daily report ----
    # Find peak hour
    peak_hour = None
    if hourly_breakdown:
        peak = max(hourly_breakdown.items(), key=lambda x: sum(x[1].values()))
        peak_hour = {"hour": peak[0], "event_count": sum(peak[1].values())}

    report = {
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

    report_key = "reports/analytics/daily/%s/report.json" % ds
    s3_client_report = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    s3_client_report.put_object(
        Bucket=data_lake_bucket,
        Key=report_key,
        Body=json.dumps(report, indent=2).encode("utf-8"),
        **bucket_owner_kwargs,
    )

    print("[%s] Generated daily analytics report: %d events, %d active users" % (
        datetime.now().strftime(_TIMESTAMP_FMT),
        summary["total_events"],
        summary["active_users"],
    ))
    print("[%s] analytics_daily.py completed successfully" % datetime.now().strftime(_TIMESTAMP_FMT))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[%s] FATAL: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), str(e)))
        sys.exit(1)
