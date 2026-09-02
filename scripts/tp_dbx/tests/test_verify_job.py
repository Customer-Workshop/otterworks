from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "databricks" / "custbill_workflow"))

from verify_job import EXPECTED_DAG, assert_job, load_snapshot, main, task_graph


@pytest.fixture
def good_settings() -> dict:
    return {
        "tasks": [
            {"task_key": "ingest", "max_retries": 2, "min_retry_interval_millis": 300000, "retry_on_timeout": False},
            {
                "task_key": "parse",
                "depends_on": [{"task_key": "ingest"}],
                "max_retries": 2,
                "min_retry_interval_millis": 300000,
                "retry_on_timeout": False,
            },
            {
                "task_key": "finance",
                "depends_on": [{"task_key": "parse"}],
                "max_retries": 2,
                "min_retry_interval_millis": 300000,
                "retry_on_timeout": False,
            },
        ],
        "max_concurrent_runs": 1,
        "schedule": {"pause_status": "PAUSED"},
        "email_notifications": {"on_failure": ["finance-reports@otterworks.dev"]},
        "parameters": [{"name": "ns"}, {"name": "report_date"}],
    }


def test_committed_snapshot_matches_before_retry_apply() -> None:
    snapshot = load_snapshot(REPO_ROOT / "databricks" / "custbill_workflow" / "job.json")
    assert assert_job(snapshot, require_retries=False) == []


def test_committed_snapshot_only_lacks_retries() -> None:
    snapshot = load_snapshot(REPO_ROOT / "databricks" / "custbill_workflow" / "job.json")
    failures = assert_job(snapshot, require_retries=True)
    assert failures
    assert all("retries" in failure or "retry" in failure for failure in failures)


def test_good_settings(good_settings: dict) -> None:
    assert assert_job(good_settings) == []


def test_reversed_dependency_mentions_finance(good_settings: dict) -> None:
    good_settings["tasks"][2]["depends_on"] = [{"task_key": "ingest"}]
    assert any("finance" in failure for failure in assert_job(good_settings))


def test_bad_concurrency(good_settings: dict) -> None:
    good_settings["max_concurrent_runs"] = 2
    assert any("max_concurrent_runs=2" in failure for failure in assert_job(good_settings))


def test_unpaused_schedule(good_settings: dict) -> None:
    good_settings["schedule"]["pause_status"] = "UNPAUSED"
    assert any("pause_status" in failure for failure in assert_job(good_settings))


def test_trigger_pause_without_schedule(good_settings: dict) -> None:
    good_settings.pop("schedule")
    good_settings["trigger"] = {"pause_status": "PAUSED", "file_arrival": {"url": "/Volumes/example"}}
    assert assert_job(good_settings) == []


def test_cluster_configuration_mentions_cluster(good_settings: dict) -> None:
    good_settings["tasks"][0]["new_cluster"] = {"spark_version": "14.3.x-scala2.12"}
    assert any("cluster" in failure for failure in assert_job(good_settings))


def test_empty_failure_notifications(good_settings: dict) -> None:
    good_settings["email_notifications"]["on_failure"] = []
    assert any("on_failure" in failure for failure in assert_job(good_settings))


def test_bad_retries(good_settings: dict) -> None:
    good_settings["tasks"][0]["max_retries"] = 0
    assert any("max_retries" in failure for failure in assert_job(good_settings))


def test_missing_report_date(good_settings: dict) -> None:
    good_settings["parameters"] = [{"name": "ns"}]
    assert any("report_date" in failure for failure in assert_job(good_settings))


def test_load_snapshot_bare_and_full_have_same_graph(tmp_path: Path, good_settings: dict) -> None:
    bare = tmp_path / "bare.json"
    full = tmp_path / "full.json"
    bare.write_text(json.dumps(good_settings))
    full.write_text(json.dumps({"job_id": 1, "settings": good_settings}))
    assert task_graph(load_snapshot(bare)) == EXPECTED_DAG
    assert task_graph(load_snapshot(bare)) == task_graph(load_snapshot(full))


def test_main_exit_codes(tmp_path: Path, good_settings: dict, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    good = tmp_path / "good.json"
    bad.write_text(json.dumps({**good_settings, "max_concurrent_runs": 2}))
    good.write_text(json.dumps(good_settings))
    assert main([str(bad)]) == 1
    assert "FAIL:" in capsys.readouterr().out
    assert main([str(good)]) == 0
    assert "PASS:" in capsys.readouterr().out
