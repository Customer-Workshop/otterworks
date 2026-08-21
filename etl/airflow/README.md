# OtterWorks ETL on Airflow

Target-state home for the five legacy cron scripts in `etl/scripts/`, migrated
per [`../ETL_UPGRADE_GUIDE.md`](../ETL_UPGRADE_GUIDE.md).

`otterworks_storage_cleanup` is the **reference DAG**: every other migration
copies its structure, its helper usage and its test layout.

## Layout

```
etl/airflow/
├── dags/
│   ├── .airflowignore              # keeps `common/` out of DAG scanning
│   ├── common/                     # shared helpers (importable as `common.*`)
│   │   ├── config.py               # connection ids + Variable keys
│   │   ├── defaults.py             # default_args / DAG kwargs contract
│   │   ├── hooks.py                # provider-hook wrappers and IO helpers
│   │   └── logging_utils.py        # namespaced loggers
│   └── otterworks_<pipeline>.py    # one module per migrated script
├── spark_jobs/                     # PySpark applications submitted by DAGs
├── tests/
│   ├── conftest.py                 # hermetic Airflow env + shared fixtures
│   ├── test_dag_integrity.py       # estate-wide contract tests
│   └── test_<pipeline>.py          # one per DAG
├── requirements.txt                # runtime pins
├── requirements-dev.txt            # + pytest / moto / pyspark
├── constraints-2.8.4-python3.11.txt
├── pytest.ini
└── check.sh                        # local verification loop
```

`common/` lives inside `dags/` on purpose: Airflow puts the DAGs folder on
`sys.path`, so `from common.defaults import dag_kwargs` resolves in the
scheduler, in the workers and in pytest without any path shims, and a
deployment that syncs only the DAGs folder still gets the helpers.

## Versions

| Component | Pin |
|-----------|-----|
| Python | 3.11 (Airflow 2.8 does not support 3.12) |
| Apache Airflow | 2.8.4 |
| `apache-airflow-providers-amazon` | 8.19.0 |
| `apache-airflow-providers-postgres` | 5.10.2 |
| `apache-airflow-providers-apache-spark` | 4.7.1 |

All installs go through `constraints-2.8.4-python3.11.txt` (the upstream
`constraints-2.8.4` file, vendored so a build is reproducible offline):

```bash
pip install -r requirements-dev.txt -c constraints-2.8.4-python3.11.txt
```

## Local verification loop

```bash
cd etl/airflow
./check.sh setup     # one-time: creates .venv on Python 3.11 with the pins above
./check.sh import    # DAG-import check — fails on any DAG import error
./check.sh test      # pytest suite (add args, e.g. ./check.sh test -k storage)
./check.sh           # import + test
```

Both legs are hermetic: a throwaway `AIRFLOW_HOME`, no example DAGs, **no
Airflow metadata database** and no network. AWS calls in tests go through
`moto`. From the repo root the same thing is available as
`make etl-airflow-check`.

CI runs both legs on every PR that touches `etl/` (`.github/workflows/etl-airflow.yml`).

## Connections

Created once per environment; **never referenced by value in code**. Use the
constants in `common/config.py`, never a literal string.

| Connection id | Type | Used for | Notes |
|---------------|------|----------|-------|
| `aws_default` | Amazon Web Services | S3, SQS, DynamoDB | Backed by an IAM role (IRSA / instance profile) or a secrets backend. Never inline keys. |
| `otterworks_postgres` | Postgres | analytics warehouse | Replaces the `[database]` block of `config.ini`. |
| `otterworks_meilisearch` | HTTP | search reindexing | Host = MeiliSearch URL, **password = master key** (replaces `meilisearch_api_key`). |
| `spark_default` | Spark | `SparkSubmitOperator` | Cluster/`yarn`/`k8s` master for the analytics PySpark job. |

## Variables

Non-sensitive configuration only. All keys are prefixed `otterworks_`, and
`common/config.py` holds both the key constant and the default the legacy
`config.ini` shipped with.

| Variable key | Default | Replaces |
|--------------|---------|----------|
| `otterworks_data_lake_bucket` | `otterworks-data-lake` | `[s3] data_lake_bucket` |
| `otterworks_file_storage_bucket` | `otterworks-file-storage` | `[s3] file_storage_bucket` |
| `otterworks_quarantine_bucket` | `otterworks-file-quarantine` | `[s3] quarantine_bucket` |
| `otterworks_archive_bucket` | `otterworks-audit-archive` | `[s3] archive_bucket` |
| `otterworks_analytics_prefix` | `analytics/daily` | `[s3] analytics_prefix` |
| `otterworks_analytics_queue_url` | `https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics` | hardcoded SQS URL in `analytics_daily.py` |
| `otterworks_analytics_events_table` | `otterworks-analytics-events` | hardcoded table name |
| `otterworks_audit_events_table` | `otterworks-audit-events` | hardcoded table name |
| `otterworks_file_metadata_table` | `otterworks-file-metadata` | hardcoded table name |
| `otterworks_document_service_url` | `http://document-service:8083` | `[services] document_service_url` |
| `otterworks_file_service_url` | `http://file-service:8082` | `[services] file_service_url` |
| `otterworks_admin_service_url` | `http://admin-service:8087` | admin-service report target |
| `otterworks_meilisearch_url` | `http://meilisearch:7700` | `[services] meilisearch_url` |
| `otterworks_spark_jobs_path` | `/opt/airflow/spark_jobs` | deploy path of `spark_jobs/` |
| `otterworks_alert_email` | `data-team@otterworks.dev` | (new) failure notifications |

Rules:

* read Variables with `common.config.get_var(KEY)` **inside a task callable**.
  A `Variable.get` at module scope hits the metadata DB on every parse loop;
* if a value is a secret, it belongs in a Connection, not a Variable;
* a new key means a change to `common/config.py`, which is foundation-owned —
  ask before adding one.

## `default_args` contract

Build DAG kwargs with `common.defaults.dag_kwargs()`, which supplies
`build_default_args()`. `tests/test_dag_integrity.py` enforces all of it:

| Setting | Value | Why |
|---------|-------|-----|
| `retries` | 3 | the cron estate had none; transient AWS/network errors lost data |
| `retry_delay` | 5 min, `retry_exponential_backoff=True`, `max_retry_delay` 30 min | back off instead of hammering a throttling API |
| `email_on_failure` | `True` (address from `otterworks_alert_email`) | no more "discovered days later" |
| `execution_timeout` | 2 h | a wedged task cannot run forever |
| `max_active_runs` | 1 | two runs must never race on the same partition |
| `catchup` | `False` | resume without a stampede; backfill explicitly |
| `owner` | `data-platform` | the estate is no longer owned by one person |
| `tags` | `["otterworks", "etl"]` | filterable in the UI |

Override only to make a task stricter (e.g. more retries for a flaky API), and
prefer a per-task override to changing the DAG default.

## Migration rules

Non-negotiable for every migrated script:

1. **`schedule` mirrors the legacy crontab** (`etl/crontab`), in UTC — not
   `@daily`, so 02:30 stays 02:30.
2. **No swallowed errors.** Every `try: except: pass` / `except: continue`
   becomes a real failure: log the context, then raise so Airflow retries and
   alerts. `common.hooks.run_with_failure_summary` does this for per-item loops
   (attempt every item, then fail with an aggregate). If the legacy script
   deliberately tolerated a partial failure, say so in the PR description —
   the behaviour change is intended, but it must be stated.
3. **Idempotency.** Key every write off the logical date (`ds` / `data_interval_start`),
   never `datetime.now()`, and make loads overwrite-in-place or upsert so that
   a retry, a re-run and a backfill all converge to the same state.
4. **Hooks only.** No `boto3.client(...)` with credentials, no `psycopg2.connect`.
5. **`logging`, not `print`.** `common.logging_utils.get_logger(__name__)`.
6. **Pure transform functions.** Keep aggregation/report building in module-level
   functions that take plain data and return plain data, so tests need no AWS.
7. **XCom carries small payloads.** Counts, keys, manifests. If a payload could
   grow past a few MB, stage it in S3 and pass the key.

## Ownership

The shared foundation — `dags/common/`, `tests/conftest.py`,
`tests/test_dag_integrity.py`, `requirements*.txt`, the constraints file,
`check.sh`, the CI workflow and this README — is owned by the migration
coordinator. A migration PR owns exactly **one** `dags/otterworks_<pipeline>.py`
plus **one** `tests/test_<pipeline>.py` (and, where applicable, its own file
under `spark_jobs/`). If a migration needs a change to anything shared, stop and
ask the coordinator instead of editing it.

## Decommissioning the legacy estate

`etl/scripts/`, `etl/crontab`, `etl/run.sh` and `etl/config.ini` stay in place
until all five DAGs are merged and verified; `config.ini` still contains
plaintext credentials, which must be **rotated** as part of its removal
(guide steps 8–9). Nothing in `etl/airflow/` reads it.
