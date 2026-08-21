"""``otterworks_storage_cleanup`` — Airflow port of etl/scripts/storage_cleanup_daily.py.

Replaces the ``30 2 * * *`` cron entry. Credentials come from the ``aws_default``
and ``otterworks_postgres`` Airflow Connections; bucket/table names come from
Airflow Variables. ``etl/config.ini`` is never read.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pendulum
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from otterworks_etl import storage_cleanup
from otterworks_etl.config import AWS_CONN_ID, POSTGRES_CONN_ID, StorageCleanupConfig

logger = logging.getLogger(__name__)

DAG_ID = "otterworks_storage_cleanup"

default_args = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "email_on_failure": True,
    "email": ["data-team@otterworks.dev"],
    "depends_on_past": False,
}


@dag(
    dag_id=DAG_ID,
    description="Quarantine orphaned S3 objects and publish a storage savings report",
    # Legacy cron entry: 30 2 * * * (daily 02:30 UTC).
    schedule="30 2 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    # The job reflects live bucket state, so historical runs would only re-observe
    # today's inventory; backfilling adds no value and would thrash quarantine.
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=default_args,
    tags=["otterworks", "storage", "migrated-from-cron"],
)
def otterworks_storage_cleanup() -> None:
    def run_date() -> str:
        """UTC date the run covers.

        ``data_interval_end`` (not ``ds``) keeps the legacy dating: the interval
        for the 02:30 run of day D ends on day D, while ``ds`` would stamp D-1.
        It is fixed per DAG run, so retries and replays reuse the same date and
        stay idempotent.
        """
        return get_current_context()["data_interval_end"].in_timezone("UTC").strftime("%Y-%m-%d")

    @task
    def list_s3_objects() -> list[dict[str, Any]]:
        config = StorageCleanupConfig.from_variables()
        return storage_cleanup.list_s3_objects(S3Hook(aws_conn_id=AWS_CONN_ID), config)

    @task
    def list_metadata_references() -> list[str]:
        config = StorageCleanupConfig.from_variables()
        return storage_cleanup.list_metadata_references(
            DynamoDBHook(aws_conn_id=AWS_CONN_ID), config
        )

    @task
    def find_orphaned_objects(
        objects: list[dict[str, Any]], referenced_keys: list[str]
    ) -> dict[str, Any]:
        return storage_cleanup.find_orphaned_objects(objects, referenced_keys)

    @task
    def move_to_quarantine(diff: dict[str, Any]) -> dict[str, Any]:
        config = StorageCleanupConfig.from_variables()
        return storage_cleanup.move_to_quarantine(
            S3Hook(aws_conn_id=AWS_CONN_ID),
            PostgresHook(postgres_conn_id=POSTGRES_CONN_ID),
            config,
            diff["orphans"],
            run_date(),
        )

    @task
    def generate_storage_report(
        diff: dict[str, Any], quarantine_result: dict[str, Any]
    ) -> str:
        config = StorageCleanupConfig.from_variables()
        report = storage_cleanup.build_report(config, run_date(), diff, quarantine_result)
        return storage_cleanup.publish_report(S3Hook(aws_conn_id=AWS_CONN_ID), config, report)

    objects = list_s3_objects()
    references = list_metadata_references()
    diff = find_orphaned_objects(objects, references)
    quarantined = move_to_quarantine(diff)
    report = generate_storage_report(diff, quarantined)

    [objects, references] >> diff >> quarantined >> report


otterworks_storage_cleanup()
