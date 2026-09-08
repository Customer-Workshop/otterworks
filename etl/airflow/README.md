# OtterWorks ETL on Apache Airflow

Airflow replacement for the legacy cron scripts in `etl/scripts/`, following
`etl/ETL_UPGRADE_GUIDE.md`.

| Legacy script                | DAG                                | Status   |
|------------------------------|------------------------------------|----------|
| `storage_cleanup_daily.py`   | `otterworks_storage_cleanup`       | migrated |
| `analytics_daily.py`         | `otterworks_analytics_etl`         | migrated |
| `audit_archive_weekly.py`    | `otterworks_audit_archive`         | pending  |
| `search_reindex_weekly.py`   | `otterworks_search_reindex`        | pending  |
| `user_activity_daily.py`     | `otterworks_user_activity_report`  | pending  |

## Layout

```
dags/
  otterworks/                      shared package (importable from DAGs and tests)
    common.py                      Connection/Variable ids, DEFAULT_ARGS (retries + backoff), logging
    storage_cleanup_transforms.py  pure functions: key formats, orphan detection, report math
    analytics_transforms.py        pure functions: key formats, SQL, aggregation, report
  otterworks_storage_cleanup.py    DAG: S3Hook + DynamoDBHook
  otterworks_analytics_etl.py      DAG: SqsHook + DynamoDBHook + S3Hook + PostgresHook
tests/                             pytest parity tests (legacy_reference.py = verbatim legacy pandas code)
docker-compose.yml                 local Airflow 3.3.1 (LocalExecutor)
requirements.txt                   pinned Airflow + providers + test toolchain
```

## Configuration

Credentials live in Airflow **Connections**, config in Airflow **Variables** —
`etl/config.ini` is no longer read.

| Kind       | Id / name                                 | Used by                          |
|------------|-------------------------------------------|----------------------------------|
| Connection | `aws_default`                             | S3Hook, SqsHook, DynamoDBHook    |
| Connection | `otterworks_postgres`                     | PostgresHook (`analytics_daily_summary`) |
| Variable   | `otterworks_data_lake_bucket`             | both DAGs (reports, data lake)   |
| Variable   | `otterworks_file_storage_bucket`          | storage cleanup                  |
| Variable   | `otterworks_quarantine_bucket`            | storage cleanup                  |
| Variable   | `otterworks_file_metadata_table`          | storage cleanup                  |
| Variable   | `otterworks_analytics_prefix`             | analytics                        |
| Variable   | `otterworks_analytics_sqs_queue_url`      | analytics                        |
| Variable   | `otterworks_analytics_events_table`       | analytics                        |
| Variable   | `otterworks_analytics_sqs_max_messages`   | analytics (legacy: 10000)        |

Both DAGs accept a `report_date` param (`YYYY-MM-DD`) for manual runs / backfills;
scheduled runs derive it from `data_interval_end`, which with the preserved cron
schedules is the same UTC calendar day the legacy scripts used.

## Run locally

```bash
cp .env.example .env          # fill in AWS/Postgres credentials and the Airflow UI user/password
docker compose up airflow-init
docker compose up -d          # http://localhost:8080 (api-server + scheduler + dag-processor)
```

## Test & lint

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt \
  -c https://raw.githubusercontent.com/apache/airflow/constraints-3.3.1/constraints-3.12.txt
pytest
ruff check dags tests && ruff format --check dags tests
```
