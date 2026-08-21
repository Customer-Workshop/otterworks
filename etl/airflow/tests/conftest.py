"""Shared pytest configuration for the OtterWorks Airflow DAG suite.

Keeps every test hermetic: a throwaway ``AIRFLOW_HOME``, no example DAGs, no
network, and no dependency on a provisioned Airflow metadata database beyond
the local SQLite file pytest creates on demand.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

AIRFLOW_DIR = Path(__file__).resolve().parents[1]
DAGS_DIR = AIRFLOW_DIR / "dags"
SPARK_JOBS_DIR = AIRFLOW_DIR / "spark_jobs"

# Airflow reads these at import time, so they must be set before `import airflow`.
os.environ.setdefault("AIRFLOW_HOME", str(AIRFLOW_DIR / ".airflow-test-home"))
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", str(DAGS_DIR))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")
os.environ.setdefault("AIRFLOW__CORE__EXECUTOR", "SequentialExecutor")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# Airflow puts the DAGs folder on sys.path at runtime; mirror that for tests so
# `from common... import` and `import otterworks_<dag>` resolve the same way.
for path in (str(DAGS_DIR), str(SPARK_JOBS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def dagbag():
    """A DagBag over the real DAGs folder, with import errors surfaced."""
    from airflow.models import DagBag

    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def _java_home_for_spark() -> str:
    """Return a JDK Spark 3.5 supports (8, 11 or 17 — not 21)."""
    current = os.environ.get("JAVA_HOME", "")
    for supported in ("-8-", "-11-", "-17-"):
        if supported in current:
            return current
    candidates = sorted(Path("/usr/lib/jvm").glob("java-17*")) + sorted(
        Path("/usr/lib/jvm").glob("java-11*")
    )
    if not candidates:
        raise RuntimeError(
            "PySpark 3.5 needs a Java 8/11/17 JDK; none found under /usr/lib/jvm "
            f"and JAVA_HOME={current!r} is unsupported"
        )
    return str(candidates[0])


@pytest.fixture(scope="session")
def spark_session():
    """Local SparkSession for testing Spark jobs without a cluster."""
    os.environ["JAVA_HOME"] = _java_home_for_spark()
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("otterworks-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture()
def aws_credentials(monkeypatch):
    """Dummy credentials so moto never reaches real AWS."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AIRFLOW_CONN_AWS_DEFAULT", "aws://?region_name=us-east-1")
