"""DAG integrity: both DAGs import cleanly and expose the guide's task graph."""

from __future__ import annotations

from datetime import timedelta

import pytest
from airflow.models import DagBag

from otterworks.common import DEFAULT_ARGS, resolve_report_date


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(include_examples=False)


def test_dags_import_without_errors(dagbag):
    assert dagbag.import_errors == {}
    assert set(dagbag.dag_ids) == {"otterworks_storage_cleanup", "otterworks_analytics_etl"}


@pytest.mark.parametrize(
    ("dag_id", "schedule", "edges"),
    [
        (
            "otterworks_storage_cleanup",
            "30 2 * * *",
            {
                "list_s3_objects": {"find_orphaned_objects"},
                "list_metadata_references": {"find_orphaned_objects"},
                "find_orphaned_objects": {"move_to_quarantine", "generate_storage_report"},
                "move_to_quarantine": {"generate_storage_report"},
                "generate_storage_report": set(),
            },
        ),
        (
            "otterworks_analytics_etl",
            "0 2 * * *",
            {
                "extract_from_sqs": {"extract_from_dynamodb", "transform_events"},
                "extract_from_dynamodb": {"transform_events"},
                "transform_events": {
                    "load_to_data_lake",
                    "update_postgres_aggregates",
                    "generate_report",
                },
                "load_to_data_lake": {"generate_report"},
                "update_postgres_aggregates": {"generate_report"},
                "generate_report": set(),
            },
        ),
    ],
)
def test_dag_structure_matches_upgrade_guide(dagbag, dag_id, schedule, edges):
    dag = dagbag.dags[dag_id]
    assert dag.schedule_interval == schedule  # legacy crontab schedule preserved
    assert dag.max_active_runs == 1
    assert dag.catchup is False
    assert "report_date" in dag.params
    assert {t.task_id: set(t.downstream_task_ids) for t in dag.tasks} == edges


def test_every_task_retries_with_exponential_backoff(dagbag):
    for dag in dagbag.dags.values():
        for task in dag.tasks:
            assert task.retries == 3, (dag.dag_id, task.task_id)
            assert task.retry_delay == timedelta(minutes=5)
            assert task.retry_exponential_backoff is True
            assert task.max_retry_delay == timedelta(minutes=30)
            assert task.on_failure_callback is not None


def test_default_args_alert_on_failure():
    assert DEFAULT_ARGS["email_on_failure"] is True
    assert DEFAULT_ARGS["retry_exponential_backoff"] is True


def test_dag_files_do_not_use_print_or_raw_clients():
    import pathlib

    dags_dir = pathlib.Path(__file__).resolve().parents[1] / "dags"
    for path in dags_dir.rglob("*.py"):
        source = path.read_text()
        assert "print(" not in source, path
        assert "boto3.client(" not in source, path
        assert "psycopg2" not in source, path
        assert "config.ini" not in source or "configparser" not in source, path


class TestResolveReportDate:
    def test_param_override_wins(self):
        from datetime import UTC, datetime

        ctx = {
            "params": {"report_date": "2023-12-31"},
            "data_interval_end": datetime(2024, 3, 7, 2, tzinfo=UTC),
        }
        assert resolve_report_date(ctx) == "2023-12-31"

    def test_scheduled_run_uses_data_interval_end_date(self):
        from datetime import UTC, datetime

        ctx = {
            "params": {"report_date": None},
            "data_interval_end": datetime(2024, 3, 7, 2, tzinfo=UTC),
        }
        assert resolve_report_date(ctx) == "2024-03-07"
