"""Unit tests for the extract / compare / quarantine / report stages."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
import pytest
from moto import mock_aws
from otterworks_etl import storage_cleanup
from otterworks_etl.config import StorageCleanupConfig

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AIRFLOW_CONN_AWS_DEFAULT", "aws://?region_name=us-east-1")

DS = "2026-08-21"


class FakePostgresHook:
    """Minimal PostgresHook stand-in that records statements and enforces the PK."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.rows: dict[tuple[str, str], tuple[str, int]] = {}

    def run(self, sql: str, parameters: Any = None) -> None:
        self.statements.append((sql, parameters))
        if sql.strip().upper().startswith("INSERT") and parameters:
            report_date, s3_key, quarantine_key, size = parameters
            self.rows.setdefault((report_date, s3_key), (quarantine_key, size))


@pytest.fixture()
def postgres_hook() -> FakePostgresHook:
    return FakePostgresHook()


@pytest.fixture()
def aws(config: StorageCleanupConfig):
    from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=config.file_storage_bucket)
        s3.create_bucket(Bucket=config.quarantine_bucket)
        s3.create_bucket(Bucket=config.data_lake_bucket)

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=config.metadata_table,
            KeySchema=[{"AttributeName": "file_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "file_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        yield {
            "s3_client": s3,
            "dynamodb": dynamodb,
            "s3_hook": S3Hook(aws_conn_id="aws_default"),
            "dynamodb_hook": DynamoDBHook(aws_conn_id="aws_default"),
        }


def put_object(aws: dict[str, Any], config: StorageCleanupConfig, key: str, body: bytes) -> None:
    aws["s3_client"].put_object(Bucket=config.file_storage_bucket, Key=key, Body=body)


def put_metadata(
    aws: dict[str, Any], config: StorageCleanupConfig, file_id: str, s3_key: str
) -> None:
    aws["dynamodb"].Table(config.metadata_table).put_item(
        Item={"file_id": file_id, "s3_key": s3_key}
    )


# --- extract -----------------------------------------------------------------


def test_list_s3_objects_returns_inventory(aws, config) -> None:
    put_object(aws, config, "files/a.txt", b"aaaa")
    put_object(aws, config, "files/nested/b.txt", b"bb")
    put_object(aws, config, "other/c.txt", b"ccc")

    objects = storage_cleanup.list_s3_objects(aws["s3_hook"], config)

    assert {obj["key"] for obj in objects} == {"files/a.txt", "files/nested/b.txt"}
    assert sum(obj["size"] for obj in objects) == 6


def test_list_s3_objects_on_empty_bucket(aws, config) -> None:
    assert storage_cleanup.list_s3_objects(aws["s3_hook"], config) == []


def test_list_metadata_references_dedupes_and_sorts(aws, config) -> None:
    put_metadata(aws, config, "f1", "files/a.txt")
    put_metadata(aws, config, "f2", "files/b.txt")
    put_metadata(aws, config, "f3", "files/a.txt".replace("a", "a"))
    aws["dynamodb"].Table(config.metadata_table).put_item(Item={"file_id": "f4"})

    assert storage_cleanup.list_metadata_references(aws["dynamodb_hook"], config) == [
        "files/a.txt",
        "files/b.txt",
    ]


def test_list_metadata_references_follows_pagination(config) -> None:
    pages = [
        {"Items": [{"s3_key": "files/a.txt"}], "LastEvaluatedKey": {"file_id": "f1"}},
        {"Items": [{"s3_key": "files/b.txt"}]},
    ]
    calls: list[dict[str, Any]] = []

    class FakeTable:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return pages[len(calls) - 1]

    class FakeHook:
        def get_conn(self) -> Any:
            return type("Res", (), {"Table": staticmethod(lambda name: FakeTable())})()

    assert storage_cleanup.list_metadata_references(FakeHook(), config) == [
        "files/a.txt",
        "files/b.txt",
    ]
    assert calls[1]["ExclusiveStartKey"] == {"file_id": "f1"}


def test_list_s3_objects_paginates_without_head_requests(config) -> None:
    pages = [
        {"Contents": [{"Key": "files/a.txt", "Size": 4}, {"Key": "files/", "Size": 0}]},
        {"Contents": [{"Key": "files/b.txt", "Size": 2}]},
    ]

    class FakePaginator:
        def paginate(self, **kwargs: Any) -> Any:
            assert kwargs == {
                "Bucket": config.file_storage_bucket,
                "Prefix": config.files_prefix,
            }
            return iter(pages)

    class FakeConn:
        def get_paginator(self, name: str) -> Any:
            assert name == "list_objects_v2"
            return FakePaginator()

    class FakeHook:
        def get_conn(self) -> Any:
            return FakeConn()

        def head_object(self, **kwargs: Any) -> Any:  # pragma: no cover - must not run
            raise AssertionError("inventory must not issue per-object HEAD requests")

    objects = storage_cleanup.list_s3_objects(FakeHook(), config)

    assert objects == [
        {"key": "files/a.txt", "size": 4},
        {"key": "files/b.txt", "size": 2},
    ]


def test_extract_failures_propagate(config) -> None:
    class ExplodingHook:
        def get_conn(self) -> Any:
            raise RuntimeError("throttled")

    with pytest.raises(RuntimeError, match="throttled"):
        storage_cleanup.list_s3_objects(ExplodingHook(), config)


# --- compare -----------------------------------------------------------------


def test_find_orphaned_objects_detects_object_without_metadata() -> None:
    objects = [
        {"key": "files/a.txt", "size": 10},
        {"key": "files/orphan.txt", "size": 25},
    ]
    diff = storage_cleanup.find_orphaned_objects(objects, ["files/a.txt"])

    assert [obj["key"] for obj in diff["orphans"]] == ["files/orphan.txt"]
    assert diff["orphaned_bytes"] == 25
    assert diff["dangling_references"] == []
    assert diff["total_objects"] == 2
    assert diff["total_size_bytes"] == 35


def test_find_orphaned_objects_reports_metadata_without_object() -> None:
    diff = storage_cleanup.find_orphaned_objects(
        [{"key": "files/a.txt", "size": 10}], ["files/a.txt", "files/ghost.txt"]
    )

    assert diff["orphans"] == []
    assert diff["dangling_references"] == ["files/ghost.txt"]


def test_find_orphaned_objects_on_empty_bucket() -> None:
    diff = storage_cleanup.find_orphaned_objects([], [])

    assert diff == {
        "orphans": [],
        "orphaned_bytes": 0,
        "dangling_references": [],
        "total_objects": 0,
        "total_size_bytes": 0,
    }


def test_find_orphaned_objects_empty_bucket_with_metadata() -> None:
    diff = storage_cleanup.find_orphaned_objects([], ["files/ghost.txt"])

    assert diff["orphans"] == []
    assert diff["dangling_references"] == ["files/ghost.txt"]


# --- quarantine --------------------------------------------------------------


def test_move_to_quarantine_copies_deletes_and_ledgers(aws, config, postgres_hook) -> None:
    put_object(aws, config, "files/orphan.txt", b"12345")
    orphans = [{"key": "files/orphan.txt", "size": 5}]

    result = storage_cleanup.move_to_quarantine(
        aws["s3_hook"], postgres_hook, config, orphans, DS
    )

    assert result["objects_quarantined"] == 1
    assert result["objects_skipped"] == 0
    dest_key = f"quarantined/{DS}/files/orphan.txt"
    assert result["quarantined_keys"] == [dest_key]
    assert aws["s3_hook"].check_for_key(key=dest_key, bucket_name=config.quarantine_bucket)
    assert not aws["s3_hook"].check_for_key(
        key="files/orphan.txt", bucket_name=config.file_storage_bucket
    )
    assert postgres_hook.rows == {(DS, "files/orphan.txt"): (dest_key, 5)}


def test_move_to_quarantine_is_idempotent_for_same_logical_date(
    aws, config, postgres_hook
) -> None:
    put_object(aws, config, "files/orphan.txt", b"12345")
    orphans = [{"key": "files/orphan.txt", "size": 5}]

    first = storage_cleanup.move_to_quarantine(
        aws["s3_hook"], postgres_hook, config, orphans, DS
    )
    second = storage_cleanup.move_to_quarantine(
        aws["s3_hook"], postgres_hook, config, orphans, DS
    )

    assert first["objects_quarantined"] == 1
    assert second["objects_quarantined"] == 0
    assert second["objects_skipped"] == 1
    quarantined = aws["s3_hook"].list_keys(
        bucket_name=config.quarantine_bucket, prefix=f"quarantined/{DS}/"
    )
    assert quarantined == [f"quarantined/{DS}/files/orphan.txt"]
    assert len(postgres_hook.rows) == 1


def test_move_to_quarantine_with_no_orphans(aws, config, postgres_hook) -> None:
    result = storage_cleanup.move_to_quarantine(aws["s3_hook"], postgres_hook, config, [], DS)

    assert result["objects_quarantined"] == 0
    assert postgres_hook.rows == {}
    # The ledger table is still ensured to exist.
    assert postgres_hook.statements[0][0].strip().startswith("CREATE TABLE IF NOT EXISTS")


def test_move_to_quarantine_failure_propagates(config, postgres_hook) -> None:
    class FailingS3Hook:
        def check_for_key(self, **kwargs: Any) -> bool:
            return False

        def copy_object(self, **kwargs: Any) -> None:
            raise RuntimeError("AccessDenied")

    with pytest.raises(RuntimeError, match="AccessDenied"):
        storage_cleanup.move_to_quarantine(
            FailingS3Hook(), postgres_hook, config, [{"key": "files/x", "size": 1}], DS
        )


# --- report ------------------------------------------------------------------


def test_build_report_shape_and_savings(config) -> None:
    diff = {
        "orphans": [{"key": "files/orphan.txt", "size": 2 * 1024**3}],
        "orphaned_bytes": 2 * 1024**3,
        "dangling_references": ["files/ghost.txt"],
        "total_objects": 4,
        "total_size_bytes": 4 * 1024**3,
    }
    quarantine_result = {"objects_quarantined": 1, "objects_skipped": 0}

    report = storage_cleanup.build_report(config, DS, diff, quarantine_result)

    assert report["report_date"] == DS
    assert report["orphans"]["orphan_percentage"] == 25.0
    assert report["orphans"]["dangling_references"] == 1
    assert report["savings"]["storage_freed_gb"] == 2.0
    assert report["savings"]["estimated_monthly_savings_usd"] == 0.046


def test_build_report_handles_empty_bucket(config) -> None:
    diff = storage_cleanup.find_orphaned_objects([], [])
    report = storage_cleanup.build_report(
        config, DS, diff, {"objects_quarantined": 0, "objects_skipped": 0}
    )

    assert report["orphans"]["orphan_percentage"] == 0
    assert report["savings"]["estimated_monthly_savings_usd"] == 0.0


def test_publish_report_is_idempotent_per_logical_date(aws, config) -> None:
    report = storage_cleanup.build_report(
        config,
        DS,
        storage_cleanup.find_orphaned_objects([], []),
        {"objects_quarantined": 0, "objects_skipped": 0},
    )

    key_one = storage_cleanup.publish_report(aws["s3_hook"], config, report)
    key_two = storage_cleanup.publish_report(aws["s3_hook"], config, report)

    assert key_one == key_two == f"reports/storage-cleanup/{DS}/report.json"
    assert aws["s3_hook"].list_keys(
        bucket_name=config.data_lake_bucket, prefix="reports/storage-cleanup/"
    ) == [key_one]
    body = aws["s3_hook"].read_key(key=key_one, bucket_name=config.data_lake_bucket)
    assert json.loads(body)["report_type"] == "storage_cleanup"
