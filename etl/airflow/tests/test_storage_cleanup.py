"""Tests for the reference DAG ``otterworks_storage_cleanup``.

Structure to copy for the other migrated scripts: pure transform functions
tested directly, IO tasks tested against moto, and the legacy behaviour that
must be preserved asserted explicitly.
"""

from __future__ import annotations

import json

import pytest

import otterworks_storage_cleanup as dag_module


@pytest.fixture()
def objects():
    return [
        {"key": "files/a.txt", "size": 100, "last_modified": "2024-05-01T00:00:00+00:00"},
        {"key": "files/b.txt", "size": 200, "last_modified": "2024-05-01T00:00:00+00:00"},
        {"key": "files/c.txt", "size": 300, "last_modified": "2024-05-01T00:00:00+00:00"},
    ]


def test_find_orphans_returns_unreferenced_objects(objects):
    result = dag_module.find_orphans(objects, ["files/b.txt"])

    assert [o["key"] for o in result["orphaned"]] == ["files/a.txt", "files/c.txt"]
    assert result["orphaned_count"] == 2
    assert result["orphaned_bytes"] == 400


def test_find_orphans_with_everything_referenced(objects):
    result = dag_module.find_orphans(objects, [o["key"] for o in objects])

    assert result["orphaned"] == []
    assert result["orphaned_bytes"] == 0


def test_find_orphans_on_empty_inventory():
    assert dag_module.find_orphans([], ["files/a.txt"])["orphaned_count"] == 0


def test_quarantine_key_is_partitioned_by_logical_date():
    assert (
        dag_module.quarantine_key("2024-05-01", "files/a.txt")
        == "quarantined/2024-05-01/files/a.txt"
    )


def test_build_report_matches_legacy_shape():
    report = dag_module.build_report(
        ds="2024-05-01",
        generated_at="2024-05-01T02:30:00+00:00",
        total_objects=4,
        total_size_bytes=4 * 1024**3,
        orphaned_count=1,
        orphaned_bytes=1024**3,
        moved_count=1,
        failed_count=0,
        quarantine_bucket="otterworks-file-quarantine",
    )

    assert report["report_type"] == "storage_cleanup"
    assert report["report_date"] == "2024-05-01"
    assert report["inventory"] == {
        "total_objects": 4,
        "total_size_bytes": 4 * 1024**3,
        "total_size_gb": 4.0,
    }
    assert report["orphans"]["orphan_percentage"] == 25.0
    assert report["orphans"]["orphaned_size_gb"] == 1.0
    assert report["cleanup"]["objects_quarantined"] == 1
    assert report["savings"]["estimated_monthly_savings_usd"] == 0.023


def test_build_report_handles_empty_bucket():
    report = dag_module.build_report(
        ds="2024-05-01",
        generated_at="2024-05-01T02:30:00+00:00",
        total_objects=0,
        total_size_bytes=0,
        orphaned_count=0,
        orphaned_bytes=0,
        moved_count=0,
        failed_count=0,
        quarantine_bucket="otterworks-file-quarantine",
    )

    assert report["orphans"]["orphan_percentage"] == 0
    assert report["savings"]["storage_freed_gb"] == 0.0


# ---------------------------------------------------------------------------
# IO tasks against moto
# ---------------------------------------------------------------------------
class FakeTI:
    def __init__(self, values):
        self._values = values

    def xcom_pull(self, task_ids):
        return self._values[task_ids]


@pytest.fixture()
def s3(aws_credentials):
    import boto3
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="otterworks-file-storage")
        client.create_bucket(Bucket="otterworks-file-quarantine")
        client.create_bucket(Bucket="otterworks-data-lake")
        yield client


def test_list_s3_objects_inventories_the_files_prefix(s3):
    s3.put_object(Bucket="otterworks-file-storage", Key="files/a.txt", Body=b"x" * 10)
    s3.put_object(Bucket="otterworks-file-storage", Key="other/b.txt", Body=b"y" * 10)

    result = dag_module.list_s3_objects()

    assert result["total_objects"] == 1
    assert result["total_size_bytes"] == 10
    assert result["objects"][0]["key"] == "files/a.txt"


def test_move_to_quarantine_copies_then_deletes(s3):
    s3.put_object(Bucket="otterworks-file-storage", Key="files/a.txt", Body=b"data")
    ti = FakeTI(
        {
            "find_orphaned_objects": {
                "orphaned": [{"key": "files/a.txt", "size": 4}],
            }
        }
    )

    moved = dag_module.move_to_quarantine(ti, ds="2024-05-01")

    assert moved == 1
    quarantined = s3.get_object(
        Bucket="otterworks-file-quarantine", Key="quarantined/2024-05-01/files/a.txt"
    )
    assert quarantined["Body"].read() == b"data"
    assert "Contents" not in s3.list_objects_v2(
        Bucket="otterworks-file-storage", Prefix="files/"
    )


def test_move_to_quarantine_is_a_noop_without_orphans(s3):
    ti = FakeTI({"find_orphaned_objects": {"orphaned": []}})

    assert dag_module.move_to_quarantine(ti, ds="2024-05-01") == 0


def test_move_to_quarantine_tolerates_objects_moved_by_an_earlier_attempt(s3):
    """A retry re-reads the same XCom, so already-moved objects must not fail it."""
    s3.put_object(Bucket="otterworks-file-storage", Key="files/b.txt", Body=b"data")
    ti = FakeTI(
        {
            "find_orphaned_objects": {
                "orphaned": [
                    {"key": "files/a.txt", "size": 4},  # moved before the failure
                    {"key": "files/b.txt", "size": 4},
                ]
            }
        }
    )

    assert dag_module.move_to_quarantine(ti, ds="2024-05-01") == 2
    assert s3.get_object(
        Bucket="otterworks-file-quarantine", Key="quarantined/2024-05-01/files/b.txt"
    )["Body"].read() == b"data"


def test_move_to_quarantine_fails_loudly(s3, monkeypatch):
    """The legacy script logged a warning and exited 0; this must raise."""
    s3.put_object(Bucket="otterworks-file-storage", Key="files/a.txt", Body=b"data")
    real_get_var = dag_module.get_var
    monkeypatch.setattr(
        dag_module,
        "get_var",
        lambda key, *args, **kwargs: (
            "otterworks-bucket-that-does-not-exist"
            if key == dag_module.VAR_QUARANTINE_BUCKET
            else real_get_var(key, *args, **kwargs)
        ),
    )
    ti = FakeTI(
        {"find_orphaned_objects": {"orphaned": [{"key": "files/a.txt", "size": 4}]}}
    )

    with pytest.raises(RuntimeError, match="quarantine"):
        dag_module.move_to_quarantine(ti, ds="2024-05-01")

    assert s3.get_object(Bucket="otterworks-file-storage", Key="files/a.txt")


def test_generate_storage_report_writes_to_the_data_lake(s3):
    ti = FakeTI(
        {
            "list_s3_objects": {"total_objects": 2, "total_size_bytes": 2048},
            "find_orphaned_objects": {"orphaned_count": 1, "orphaned_bytes": 1024},
            "move_to_quarantine": 1,
        }
    )

    key = dag_module.generate_storage_report(
        ti, ds="2024-05-01", ts="2024-05-01T02:30:00+00:00"
    )

    assert key == "reports/storage-cleanup/2024-05-01/report.json"
    body = s3.get_object(Bucket="otterworks-data-lake", Key=key)["Body"].read()
    report = json.loads(body)
    assert report["cleanup"]["objects_quarantined"] == 1
    assert report["report_date"] == "2024-05-01"


def test_generate_storage_report_is_idempotent(s3):
    ti = FakeTI(
        {
            "list_s3_objects": {"total_objects": 1, "total_size_bytes": 10},
            "find_orphaned_objects": {"orphaned_count": 0, "orphaned_bytes": 0},
            "move_to_quarantine": 0,
        }
    )

    first = dag_module.generate_storage_report(ti, ds="2024-05-01", ts="t1")
    second = dag_module.generate_storage_report(ti, ds="2024-05-01", ts="t1")

    assert first == second
    listing = s3.list_objects_v2(Bucket="otterworks-data-lake", Prefix="reports/")
    assert listing["KeyCount"] == 1


def test_dag_structure(dagbag):
    dag = dagbag.dags["otterworks_storage_cleanup"]

    assert dag.schedule_interval == "30 2 * * *"
    assert set(dag.task_ids) == {
        "list_s3_objects",
        "list_metadata_references",
        "find_orphaned_objects",
        "move_to_quarantine",
        "generate_storage_report",
    }
    assert set(dag.get_task("find_orphaned_objects").upstream_task_ids) == {
        "list_s3_objects",
        "list_metadata_references",
    }
    assert dag.get_task("move_to_quarantine").downstream_task_ids == {
        "generate_storage_report"
    }
