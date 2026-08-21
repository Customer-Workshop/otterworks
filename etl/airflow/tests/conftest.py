from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

AIRFLOW_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("AIRFLOW_HOME", str(AIRFLOW_ROOT / ".airflow"))
os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", str(AIRFLOW_ROOT / "dags"))

sys.path.insert(0, str(AIRFLOW_ROOT / "plugins"))
sys.path.insert(0, str(AIRFLOW_ROOT / "dags"))

from otterworks_etl.config import StorageCleanupConfig  # noqa: E402


@pytest.fixture()
def config() -> StorageCleanupConfig:
    return StorageCleanupConfig(
        file_storage_bucket="otterworks-file-storage",
        quarantine_bucket="otterworks-file-quarantine",
        data_lake_bucket="otterworks-data-lake",
        metadata_table="otterworks-file-metadata",
        files_prefix="files/",
        quarantine_prefix="quarantined",
        ledger_table="etl_storage_quarantine_ledger",
    )
