"""Shared fixtures: an isolated AIRFLOW_HOME and the legacy script sources."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

AIRFLOW_DIR = Path(__file__).resolve().parents[1]
DAGS_DIR = AIRFLOW_DIR / "dags"
LEGACY_SCRIPTS_DIR = AIRFLOW_DIR.parent / "scripts"

# Airflow puts DAGS_FOLDER on sys.path at runtime; mirror that for tests so
# `from otterworks... import` resolves for both the DAG files and the tests.
if str(DAGS_DIR) not in sys.path:
    sys.path.insert(0, str(DAGS_DIR))

os.environ.setdefault("AIRFLOW_HOME", str(AIRFLOW_DIR / ".airflow-test-home"))
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", str(DAGS_DIR))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")
os.environ.setdefault("AIRFLOW__LOGGING__LOGGING_LEVEL", "WARNING")
# moto needs *some* credentials; the hooks fall back to the boto3 default chain
# when the `aws_default` Connection is absent.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="session")
def legacy_analytics_source() -> str:
    return (LEGACY_SCRIPTS_DIR / "analytics_daily.py").read_text()


@pytest.fixture(scope="session")
def legacy_storage_cleanup_source() -> str:
    return (LEGACY_SCRIPTS_DIR / "storage_cleanup_daily.py").read_text()


@pytest.fixture
def report_date() -> str:
    return "2024-03-07"
