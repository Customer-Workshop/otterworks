"""Connection ids and Airflow Variable keys for the OtterWorks ETL DAGs.

Everything that used to live in ``etl/config.ini`` is resolved here:

* secrets (AWS keys, Postgres password, MeiliSearch master key) come from
  Airflow **Connections** and are never referenced by value in code;
* non-sensitive settings (bucket names, table names, service URLs) come from
  Airflow **Variables** whose keys are declared below.

Variables must only be resolved **inside task callables**. Calling
``Variable.get`` at module scope makes the scheduler hit the metadata database
on every DAG parse.
"""

from __future__ import annotations

from typing import Any

from airflow.models import Variable

# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------
AWS_CONN_ID = "aws_default"
POSTGRES_CONN_ID = "otterworks_postgres"
MEILISEARCH_CONN_ID = "otterworks_meilisearch"
SPARK_CONN_ID = "spark_default"

# --------------------------------------------------------------------------
# Variable keys (all prefixed ``otterworks_``)
# --------------------------------------------------------------------------
VAR_DATA_LAKE_BUCKET = "otterworks_data_lake_bucket"
VAR_FILE_STORAGE_BUCKET = "otterworks_file_storage_bucket"
VAR_QUARANTINE_BUCKET = "otterworks_quarantine_bucket"
VAR_ARCHIVE_BUCKET = "otterworks_archive_bucket"

VAR_ANALYTICS_PREFIX = "otterworks_analytics_prefix"
VAR_ANALYTICS_QUEUE_URL = "otterworks_analytics_queue_url"

VAR_ANALYTICS_EVENTS_TABLE = "otterworks_analytics_events_table"
VAR_AUDIT_EVENTS_TABLE = "otterworks_audit_events_table"
VAR_FILE_METADATA_TABLE = "otterworks_file_metadata_table"

VAR_DOCUMENT_SERVICE_URL = "otterworks_document_service_url"
VAR_FILE_SERVICE_URL = "otterworks_file_service_url"
VAR_ADMIN_SERVICE_URL = "otterworks_admin_service_url"
VAR_MEILISEARCH_URL = "otterworks_meilisearch_url"

VAR_SPARK_JOBS_PATH = "otterworks_spark_jobs_path"
VAR_ALERT_EMAIL = "otterworks_alert_email"

#: Defaults applied when a Variable has not been provisioned yet. They mirror
#: the values the legacy ``config.ini`` shipped with, so a fresh environment
#: behaves exactly like the cron estate did.
VARIABLE_DEFAULTS: dict[str, str] = {
    VAR_DATA_LAKE_BUCKET: "otterworks-data-lake",
    VAR_FILE_STORAGE_BUCKET: "otterworks-file-storage",
    VAR_QUARANTINE_BUCKET: "otterworks-file-quarantine",
    VAR_ARCHIVE_BUCKET: "otterworks-audit-archive",
    VAR_ANALYTICS_PREFIX: "analytics/daily",
    VAR_ANALYTICS_QUEUE_URL: (
        "https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics"
    ),
    VAR_ANALYTICS_EVENTS_TABLE: "otterworks-analytics-events",
    VAR_AUDIT_EVENTS_TABLE: "otterworks-audit-events",
    VAR_FILE_METADATA_TABLE: "otterworks-file-metadata",
    VAR_DOCUMENT_SERVICE_URL: "http://document-service:8083",
    VAR_FILE_SERVICE_URL: "http://file-service:8082",
    VAR_ADMIN_SERVICE_URL: "http://admin-service:8087",
    VAR_MEILISEARCH_URL: "http://meilisearch:7700",
    VAR_SPARK_JOBS_PATH: "/opt/airflow/spark_jobs",
    VAR_ALERT_EMAIL: "data-team@otterworks.dev",
}


def get_var(key: str, default: Any = None, deserialize_json: bool = False) -> Any:
    """Read an Airflow Variable, falling back to :data:`VARIABLE_DEFAULTS`.

    Call this from inside a task callable, never at DAG parse time.
    """
    fallback = default if default is not None else VARIABLE_DEFAULTS.get(key)
    return Variable.get(key, default_var=fallback, deserialize_json=deserialize_json)


def require_var(key: str) -> str:
    """Read a Variable that has no safe default and fail loudly if it is unset."""
    value = Variable.get(key, default_var=VARIABLE_DEFAULTS.get(key))
    if value is None or value == "":
        raise ValueError(f"Airflow Variable '{key}' is not set")
    return str(value)
