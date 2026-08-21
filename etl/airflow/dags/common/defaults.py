"""Shared DAG defaults for the OtterWorks ETL estate.

Every DAG in this folder must build its ``default_args`` through
:func:`build_default_args` and its DAG kwargs through :func:`dag_kwargs` so the
retry, alerting and concurrency contract is identical across the estate.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from .config import VAR_ALERT_EMAIL, VARIABLE_DEFAULTS

#: Owner recorded on every DAG and task.
DEFAULT_OWNER = "data-platform"

#: All DAGs share one start date so backfills line up across the estate.
DEFAULT_START_DATE = datetime(2024, 1, 1)

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = timedelta(minutes=5)
DEFAULT_MAX_RETRY_DELAY = timedelta(minutes=30)
DEFAULT_EXECUTION_TIMEOUT = timedelta(hours=2)


def alert_email() -> str:
    """Failure-notification address.

    Read from the environment rather than the Variables table because
    ``default_args`` is evaluated at DAG parse time, and parse-time Variable
    lookups hit the metadata database on every scheduler loop. Airflow exposes
    Variables as ``AIRFLOW_VAR_<KEY>`` environment variables, so setting the
    Variable through the env-var backend keeps a single source of truth.
    """
    env_key = f"AIRFLOW_VAR_{VAR_ALERT_EMAIL.upper()}"
    return os.environ.get(env_key, VARIABLE_DEFAULTS[VAR_ALERT_EMAIL])


def build_default_args(**overrides: Any) -> dict[str, Any]:
    """Return the shared ``default_args`` mapping.

    Contract (do not weaken it in a DAG):

    * ``retries=3`` with a 5 minute base delay and **exponential backoff**
      capped at 30 minutes — the legacy scripts had no retries at all and lost
      data on transient AWS/network errors;
    * ``email_on_failure=True`` so a failed task is never silent;
    * ``execution_timeout`` so a wedged task cannot run forever.

    Pass overrides only to make a task *stricter* (e.g. more retries for a
    flaky API), and prefer per-task overrides over changing the DAG default.
    """
    args: dict[str, Any] = {
        "owner": DEFAULT_OWNER,
        "depends_on_past": False,
        "start_date": DEFAULT_START_DATE,
        "email": [alert_email()],
        "email_on_failure": True,
        "email_on_retry": False,
        "retries": DEFAULT_RETRIES,
        "retry_delay": DEFAULT_RETRY_DELAY,
        "retry_exponential_backoff": True,
        "max_retry_delay": DEFAULT_MAX_RETRY_DELAY,
        "execution_timeout": DEFAULT_EXECUTION_TIMEOUT,
    }
    args.update(overrides)
    return args


def dag_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return the shared DAG-level kwargs.

    ``max_active_runs=1`` replaces the implicit serialisation cron gave us and
    stops two runs of the same pipeline from racing on the same S3 partition.
    ``catchup=False`` keeps a paused-then-resumed DAG from stampeding; run
    backfills explicitly instead.
    """
    kwargs: dict[str, Any] = {
        "max_active_runs": 1,
        "catchup": False,
        "default_args": build_default_args(),
        "tags": ["otterworks", "etl"],
    }
    kwargs.update(overrides)
    return kwargs
