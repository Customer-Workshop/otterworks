"""Structured logging for OtterWorks DAGs.

Replaces the legacy ``print("[%s] ..." % now)`` pattern. Airflow installs its
own handlers on the root logger, so task code only needs a named logger; the
timestamp, level and task context are added by Airflow's formatter.
"""

from __future__ import annotations

import logging

LOGGER_NAMESPACE = "otterworks.etl"


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for a DAG module or helper.

    Pass ``__name__`` from the calling module. The returned logger is a child
    of ``otterworks.etl`` so every ETL log line can be filtered downstream by
    a single prefix.
    """
    suffix = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{suffix}")
