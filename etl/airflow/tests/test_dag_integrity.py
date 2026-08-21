"""Estate-wide contract tests.

Every DAG added to ``etl/airflow/dags/`` is checked here automatically. These
assertions encode the shared contract described in ``etl/airflow/README.md``;
a DAG that cannot satisfy one of them needs a change to the shared helpers
(owned by the foundation), not a local exception.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from conftest import DAGS_DIR


def test_no_import_errors(dagbag):
    assert not dagbag.import_errors, f"DAG import errors: {dagbag.import_errors}"


def test_every_dag_module_defines_a_dag(dagbag):
    """Each top-level module in ``dags/`` must contribute at least one DAG."""
    modules = {
        path.stem
        for path in Path(DAGS_DIR).glob("*.py")
        if not path.name.startswith("_")
    }
    assert modules, "no DAG modules found"
    contributing = {
        Path(dag.fileloc).stem for dag in dagbag.dags.values()
    }
    assert modules == contributing, (
        "DAG modules with no DAG object: " f"{sorted(modules - contributing)}"
    )


@pytest.fixture()
def dags(dagbag):
    # `dagbag.dags` avoids `get_dag`, which would query the metadata database.
    return [dag for _, dag in sorted(dagbag.dags.items())]


def test_dag_ids_are_namespaced(dags):
    for dag in dags:
        assert dag.dag_id.startswith("otterworks_"), dag.dag_id


def test_dags_have_tasks_and_no_cycles(dags):
    from airflow.utils.dag_cycle_tester import check_cycle

    for dag in dags:
        assert dag.tasks, f"{dag.dag_id} has no tasks"
        check_cycle(dag)


def test_dags_are_serialised_singly(dags):
    for dag in dags:
        assert dag.max_active_runs == 1, dag.dag_id
        assert dag.catchup is False, dag.dag_id


def test_dags_are_scheduled(dags):
    for dag in dags:
        assert dag.schedule_interval is not None, dag.dag_id


def test_retry_contract(dags):
    for dag in dags:
        for task in dag.tasks:
            where = f"{dag.dag_id}.{task.task_id}"
            assert task.retries >= 3, where
            assert task.retry_delay >= timedelta(minutes=5), where
            assert task.retry_exponential_backoff is True, where
            assert task.max_retry_delay is not None, where


def test_alerting_contract(dags):
    for dag in dags:
        for task in dag.tasks:
            where = f"{dag.dag_id}.{task.task_id}"
            assert task.email_on_failure is True, where
            assert task.email, where
            assert task.owner == "data-platform", where


def test_execution_timeout_is_set(dags):
    for dag in dags:
        for task in dag.tasks:
            assert task.execution_timeout is not None, f"{dag.dag_id}.{task.task_id}"


def test_dags_are_documented(dags):
    for dag in dags:
        assert dag.doc_md, f"{dag.dag_id} has no doc_md"
        assert dag.tags and "otterworks" in dag.tags, dag.dag_id
