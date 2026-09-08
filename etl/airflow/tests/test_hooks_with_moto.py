"""Hook-backed extract/load helpers against moto (no live AWS, no Postgres)."""

from __future__ import annotations

import gzip
import json

import boto3
import pytest
from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.hooks.sqs import SqsHook
from moto import mock_aws

import otterworks_analytics_etl as analytics
import otterworks_storage_cleanup as storage
from otterworks.analytics_transforms import aggregate_events

REGION = "us-east-1"


@pytest.fixture
def aws():
    with mock_aws():
        yield


def _make_table(name: str, key: str) -> None:
    boto3.resource("dynamodb", region_name=REGION).create_table(
        TableName=name,
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


class TestStorageCleanupHooks:
    def test_inventory_orphans_and_quarantine_move(self, aws, report_date):
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket="files")
        s3.create_bucket(Bucket="quarantine")
        for key, body in (("files/keep", b"k"), ("files/orphan", b"oo"), ("other/x", b"x")):
            s3.put_object(Bucket="files", Key=key, Body=body)
        _make_table("meta", "file_id")
        boto3.resource("dynamodb", region_name=REGION).Table("meta").put_item(
            Item={"file_id": "1", "s3_key": "files/keep"}
        )

        objects = storage.list_s3_objects("files", "files/", S3Hook(aws_conn_id=None))
        assert sorted(o["key"] for o in objects) == ["files/keep", "files/orphan"]
        assert all(set(o) == {"key", "size", "last_modified"} for o in objects)

        referenced = storage.list_metadata_references("meta", DynamoDBHook(aws_conn_id=None))
        assert referenced == ["files/keep"]

        orphaned = [o for o in objects if o["key"] not in set(referenced)]
        result = storage.move_to_quarantine(
            orphaned,
            source_bucket="files",
            quarantine_bucket="quarantine",
            report_date=report_date,
            s3_hook=S3Hook(aws_conn_id=None),
        )
        assert result == {"moved_count": 1, "failed_count": 0}
        remaining = {o["Key"] for o in s3.list_objects_v2(Bucket="files")["Contents"]}
        assert remaining == {"files/keep", "other/x"}
        moved = s3.get_object(Bucket="quarantine", Key=f"quarantined/{report_date}/files/orphan")
        assert moved["Body"].read() == b"oo"


class TestAnalyticsHooks:
    def test_sqs_extract_deletes_parsed_and_keeps_malformed(self, aws):
        sqs = boto3.client("sqs", region_name=REGION)
        url = sqs.create_queue(QueueName="analytics")["QueueUrl"]
        for i in range(12):
            sqs.send_message(QueueUrl=url, MessageBody=json.dumps({"eventType": "login", "i": i}))
        sqs.send_message(QueueUrl=url, MessageBody="{not json")

        events = analytics.extract_from_sqs(url, 10_000, SqsHook(aws_conn_id=None))
        assert sorted(e["i"] for e in events) == list(range(12))

        attrs = sqs.get_queue_attributes(
            QueueUrl=url, AttributeNames=["ApproximateNumberOfMessagesNotVisible"]
        )["Attributes"]
        # the malformed message is the only one still on the queue (in-flight)
        assert int(attrs["ApproximateNumberOfMessagesNotVisible"]) == 1

    def test_sqs_extract_honours_max_messages(self, aws):
        sqs = boto3.client("sqs", region_name=REGION)
        url = sqs.create_queue(QueueName="analytics")["QueueUrl"]
        for i in range(25):
            sqs.send_message(QueueUrl=url, MessageBody=json.dumps({"i": i}))
        events = analytics.extract_from_sqs(url, 20, SqsHook(aws_conn_id=None))
        assert len(events) == 20

    def test_dynamodb_extract_filters_by_date_and_normalises_decimals(self, aws, report_date):
        _make_table("events", "event_id")
        table = boto3.resource("dynamodb", region_name=REGION).Table("events")
        table.put_item(
            Item={
                "event_id": "1",
                "event_date": f"{report_date}T10:00:00Z",
                "eventType": "file_uploaded",
                "sizeBytes": 2048,
            }
        )
        table.put_item(Item={"event_id": "2", "event_date": "2024-03-06T10:00:00Z"})

        events = analytics.extract_from_dynamodb(
            "events", report_date, DynamoDBHook(aws_conn_id=None)
        )
        assert len(events) == 1
        assert events[0]["sizeBytes"] == 2048 and type(events[0]["sizeBytes"]) is int

    def test_load_to_data_lake_writes_legacy_partition(self, aws, report_date):
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket="lake")
        aggregates = aggregate_events(
            [{"eventType": "document_created", "ownerId": "u1", "documentId": "d1"}]
        )
        keys = analytics.load_to_data_lake(
            aggregates,
            bucket="lake",
            analytics_prefix="analytics/daily",
            report_date=report_date,
            s3_hook=S3Hook(aws_conn_id=None),
        )
        base = "analytics/daily/year=2024/month=03/day=07"
        assert keys == [
            f"{base}/summary.json.gz",
            f"{base}/hourly_breakdown.json.gz",
            f"{base}/top_users.jsonl.gz",
        ]
        summary = s3.get_object(Bucket="lake", Key=keys[0])["Body"].read()
        assert json.loads(gzip.decompress(summary)) == aggregates["summary"]
        users = gzip.decompress(s3.get_object(Bucket="lake", Key=keys[2])["Body"].read())
        assert [json.loads(line) for line in users.splitlines()] == aggregates["user_summaries"]
