"""DAG-level tests: import errors, schedule, and task graph."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.models import DagBag

DAG_ID = "otterworks_storage_cleanup"
DAGS_FOLDER = Path(__file__).resolve().parents[1] / "dags"

EXPECTED_DEPENDENCIES = {
    "list_s3_objects": {"find_orphaned_objects"},
    "list_metadata_references": {"find_orphaned_objects"},
    "find_orphaned_objects": {"move_to_quarantine", "generate_storage_report"},
    "move_to_quarantine": {"generate_storage_report"},
    "generate_storage_report": set(),
}


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_FOLDER), include_examples=False)


def test_dagbag_has_no_import_errors(dagbag: DagBag) -> None:
    assert dagbag.import_errors == {}


def test_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_schedule_is_daily_at_0230_utc(dagbag: DagBag) -> None:
    dag = dagbag.dags[DAG_ID]
    assert dag.schedule_interval == "30 2 * * *"
    assert dag.timezone.name == "UTC"


def test_run_policy(dagbag: DagBag) -> None:
    dag = dagbag.dags[DAG_ID]
    assert dag.max_active_runs == 1
    assert dag.catchup is False


def test_retry_policy_has_exponential_backoff(dagbag: DagBag) -> None:
    dag = dagbag.dags[DAG_ID]
    for task in dag.tasks:
        assert task.retries == 3
        assert task.retry_delay == timedelta(minutes=5)
        assert task.retry_exponential_backoff is True
        assert task.max_retry_delay == timedelta(minutes=30)


def test_task_graph(dagbag: DagBag) -> None:
    dag = dagbag.dags[DAG_ID]
    assert set(dag.task_ids) == set(EXPECTED_DEPENDENCIES)
    for task_id, downstream in EXPECTED_DEPENDENCIES.items():
        assert set(dag.get_task(task_id).downstream_task_ids) == downstream


def test_extract_tasks_have_no_upstream(dagbag: DagBag) -> None:
    dag = dagbag.dags[DAG_ID]
    for task_id in ("list_s3_objects", "list_metadata_references"):
        assert dag.get_task(task_id).upstream_task_ids == set()


def test_dag_uses_hooks_and_never_reads_config_ini() -> None:
    sources = list(DAGS_FOLDER.rglob("*.py")) + list(
        (DAGS_FOLDER.parent / "plugins").rglob("*.py")
    )
    forbidden = ("configparser", "config.read(", "boto3.client(", "boto3.resource(", "psycopg2")
    for path in sources:
        code = "\n".join(
            line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
        )
        for token in forbidden:
            assert token not in code, f"{path.name} still uses {token}"
