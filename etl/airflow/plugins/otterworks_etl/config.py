"""Configuration access for the OtterWorks Airflow ETL DAGs.

All non-sensitive settings come from Airflow Variables; every credential comes
from an Airflow Connection (``aws_default``, ``otterworks_postgres``). Nothing
is read from ``etl/config.ini`` and no secret is stored in this repository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from airflow.models import Variable

logger = logging.getLogger(__name__)

AWS_CONN_ID = "aws_default"
POSTGRES_CONN_ID = "otterworks_postgres"

DEFAULTS = {
    "otterworks_file_storage_bucket": "otterworks-file-storage",
    "otterworks_quarantine_bucket": "otterworks-file-quarantine",
    "otterworks_data_lake_bucket": "otterworks-data-lake",
    "otterworks_file_metadata_table": "otterworks-file-metadata",
    "otterworks_files_prefix": "files/",
    "otterworks_quarantine_prefix": "quarantined",
    "otterworks_quarantine_ledger_table": "etl_storage_quarantine_ledger",
}

# S3 standard storage, USD per GB-month, used for the savings estimate.
STORAGE_COST_PER_GB_MONTH = 0.023


@dataclass(frozen=True)
class StorageCleanupConfig:
    """Resolved, non-sensitive configuration for the storage cleanup DAG."""

    file_storage_bucket: str
    quarantine_bucket: str
    data_lake_bucket: str
    metadata_table: str
    files_prefix: str
    quarantine_prefix: str
    ledger_table: str

    @classmethod
    def from_variables(cls) -> StorageCleanupConfig:
        values = {key: Variable.get(key, default_var=default) for key, default in DEFAULTS.items()}
        logger.info(
            "Resolved storage cleanup configuration: source=s3://%s/%s metadata_table=%s quarantine=s3://%s/%s",
            values["otterworks_file_storage_bucket"],
            values["otterworks_files_prefix"],
            values["otterworks_file_metadata_table"],
            values["otterworks_quarantine_bucket"],
            values["otterworks_quarantine_prefix"],
        )
        return cls(
            file_storage_bucket=values["otterworks_file_storage_bucket"],
            quarantine_bucket=values["otterworks_quarantine_bucket"],
            data_lake_bucket=values["otterworks_data_lake_bucket"],
            metadata_table=values["otterworks_file_metadata_table"],
            files_prefix=values["otterworks_files_prefix"],
            quarantine_prefix=values["otterworks_quarantine_prefix"],
            ledger_table=values["otterworks_quarantine_ledger_table"],
        )
