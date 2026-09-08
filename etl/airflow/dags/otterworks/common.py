"""DAG-wide defaults, Connection/Variable names and logging helpers."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from airflow.models import Variable

# ---- Airflow Connections (credentials live here, never in the repo) ----
AWS_CONN_ID = "aws_default"
POSTGRES_CONN_ID = "otterworks_postgres"

# ---- Airflow Variables (non-sensitive config, replaces etl/config.ini) ----
# Defaults mirror the legacy config.ini so a fresh Airflow install parses and
# runs the DAGs; override per environment in the Airflow UI / secrets backend.
VARIABLE_DEFAULTS: dict[str, str] = {
    "otterworks_data_lake_bucket": "otterworks-data-lake",
    "otterworks_file_storage_bucket": "otterworks-file-storage",
    "otterworks_quarantine_bucket": "otterworks-file-quarantine",
    "otterworks_analytics_prefix": "analytics/daily",
    "otterworks_analytics_sqs_queue_url": (
        "https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics"
    ),
    "otterworks_analytics_events_table": "otterworks-analytics-events",
    "otterworks_file_metadata_table": "otterworks-file-metadata",
    "otterworks_analytics_sqs_max_messages": "10000",
}

ALERT_EMAIL = os.environ.get("OTTERWORKS_ALERT_EMAIL", "data-team@otterworks.dev")


def get_variable(name: str) -> str:
    """Read an Airflow Variable, falling back to the legacy config.ini value."""
    return Variable.get(name, default_var=VARIABLE_DEFAULTS[name])


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_task_failure(context: dict[str, Any]) -> None:
    """``on_failure_callback``: emit a structured failure record.

    Hook point for Slack / PagerDuty; the legacy scripts only printed to
    /var/log/etl and swallowed most errors.
    """
    ti = context["task_instance"]
    logging.getLogger("otterworks.alerts").error(
        "task_failed dag_id=%s task_id=%s run_id=%s try_number=%s exception=%s",
        ti.dag_id,
        ti.task_id,
        context.get("run_id"),
        ti.try_number,
        context.get("exception"),
    )


DEFAULT_ARGS: dict[str, Any] = {
    "owner": "data-team",
    "email": [ALERT_EMAIL],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": log_task_failure,
}


def resolve_report_date(context: dict[str, Any]) -> str:
    """Return the ``YYYY-MM-DD`` report date for a run.

    The legacy scripts used the wall-clock UTC date at run time. With the
    legacy cron schedules preserved (``0 2 * * *`` etc.) ``data_interval_end``
    is that same calendar day, and ``params.report_date`` lets manual /
    backfill runs target any date.
    """
    override = (context.get("params") or {}).get("report_date")
    if override:
        return str(override)
    interval_end = context.get("data_interval_end")
    if interval_end is None:
        return datetime.now(tz=UTC).strftime("%Y-%m-%d")
    return interval_end.strftime("%Y-%m-%d")


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
