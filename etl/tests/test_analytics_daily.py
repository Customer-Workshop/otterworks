import gzip
import json
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import pytest


def _bucket(s3, name):
    s3.create_bucket(Bucket=name)


def _table(dynamodb, name, key_types):
    return dynamodb.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": key, "KeyType": kind} for key, kind in key_types],
        AttributeDefinitions=[
            {"AttributeName": key, "AttributeType": "S"} for key, _ in key_types
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _read_gzip_json(s3, bucket, key):
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(gzip.decompress(body))


def test_analytics_aggregates_sqs_and_dynamodb_events(
    moto_aws, etl_config, load_script, postgres_service
):
    region = "us-east-1"
    s3 = boto3.client("s3", region_name=region)
    _bucket(s3, "otterworks-data-lake")
    sqs = boto3.client("sqs", region_name=region)
    queue_url = sqs.create_queue(QueueName="otterworks-analytics")["QueueUrl"]
    assert queue_url.endswith("/otterworks-analytics")
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = _table(
        dynamodb,
        "otterworks-analytics-events",
        [("event_id", "HASH"), ("event_date", "RANGE")],
    )
    ds = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events = [
        {"eventType": "document_created", "ownerId": "alice", "documentId": "d1", "timestamp": f"{ds}T09:01:00Z"},
        {"eventType": "document_edited", "editedBy": "bob", "documentId": "d1", "timestamp": f"{ds}T09:02:00Z"},
        {"eventType": "comment_added", "authorId": "alice", "documentId": "d1", "timestamp": f"{ds}T09:03:00Z"},
        {"eventType": "file_uploaded", "userId": "carol", "fileId": "f1", "sizeBytes": 100, "timestamp": f"{ds}T09:04:00Z"},
        {"eventType": "file_shared", "ownerId": "alice", "fileId": "f1", "timestamp": f"{ds}T09:05:00Z"},
        {"eventType": "file_deleted", "userId": "bob", "fileId": "f2", "timestamp": f"{ds}T10:01:00Z"},
        {"eventType": "document_edited", "ownerId": "bob", "documentId": "d2", "timestamp": f"{ds}T10:02:00Z"},
        {"eventType": "document_created", "ownerId": None, "documentId": None, "timestamp": f"{ds}T09:06:00Z"},
        {"eventType": "file_uploaded", "userId": "", "fileId": "f3", "timestamp": f"{ds}T09:07:00Z"},
    ]
    for event in events:
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(event))
    sqs.send_message(QueueUrl=queue_url, MessageBody="not-json")
    table.put_item(
        Item={
            "event_id": "ddb-1",
            "event_date": f"{ds}T09:08:00Z",
            "eventType": "document_created",
            "ownerId": "dave",
            "documentId": "d3",
            "sizeBytes": Decimal("50"),
            "timestamp": f"{ds}T09:08:00Z",
        }
    )
    table.put_item(
        Item={
            "event_id": "ddb-2",
            "event_date": f"{ds}T11:00:00Z",
            "eventType": "file_uploaded",
            "userId": "dave",
            "fileId": "f4",
            "sizeBytes": Decimal("25.5"),
            "timestamp": f"{ds}T11:00:00Z",
        }
    )
    etl_config(database_port=postgres_service["port"])

    load_script("analytics_daily.py").main()

    prefix = f"analytics/daily/year={ds[:4]}/month={ds[5:7]}/day={ds[8:10]}"
    summary = _read_gzip_json(s3, "otterworks-data-lake", f"{prefix}/summary.json.gz")
    assert summary["active_users"] == 4
    assert summary["active_documents"] == 3
    assert summary["active_files"] == 4
    assert summary["total_events"] == 11
    assert summary["documents_created"] == 3
    assert summary["files_uploaded"] == 3
    assert summary["bytes_uploaded"] == 125
    hourly = _read_gzip_json(s3, "otterworks-data-lake", f"{prefix}/hourly_breakdown.json.gz")
    assert max(hourly, key=lambda hour: sum(hourly[hour].values())) == "09"
    users = gzip.decompress(
        s3.get_object(Bucket="otterworks-data-lake", Key=f"{prefix}/top_users.jsonl.gz")["Body"].read()
    ).decode().strip().splitlines()
    assert json.loads(users[0])["user_id"] == "alice"
    report = json.loads(
        s3.get_object(
            Bucket="otterworks-data-lake",
            Key=f"reports/analytics/daily/{ds}/report.json",
        )["Body"].read()
    )
    assert report["highlights"]["peak_hour"] == {"hour": "09", "event_count": 8}


def test_analytics_empty_input_exits_zero(moto_aws, etl_config, load_script):
    s3 = boto3.client("s3", region_name="us-east-1")
    _bucket(s3, "otterworks-data-lake")
    sqs = boto3.client("sqs", region_name="us-east-1")
    sqs.create_queue(QueueName="otterworks-analytics")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    _table(dynamodb, "otterworks-analytics-events", [("event_id", "HASH"), ("event_date", "RANGE")])

    with pytest.raises(SystemExit) as exc:
        load_script("analytics_daily.py").main()
    assert exc.value.code == 0


def test_analytics_single_event_with_nan_fields(
    moto_aws, etl_config, load_script, postgres_service
):
    s3 = boto3.client("s3", region_name="us-east-1")
    _bucket(s3, "otterworks-data-lake")
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue_url = sqs.create_queue(QueueName="otterworks-analytics")["QueueUrl"]
    ds = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(
            {
                "eventType": "file_uploaded",
                "ownerId": None,
                "userId": None,
                "fileId": None,
                "sizeBytes": None,
                "timestamp": f"{ds}T23:59:00Z",
            }
        ),
    )
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    _table(dynamodb, "otterworks-analytics-events", [("event_id", "HASH"), ("event_date", "RANGE")])
    etl_config(database_port=postgres_service["port"])

    load_script("analytics_daily.py").main()

    prefix = f"analytics/daily/year={ds[:4]}/month={ds[5:7]}/day={ds[8:10]}"
    summary = _read_gzip_json(s3, "otterworks-data-lake", f"{prefix}/summary.json.gz")
    assert summary["total_events"] == 1
    assert summary["files_uploaded"] == 1
    assert summary["bytes_uploaded"] == 0
    assert summary["active_users"] == 0
