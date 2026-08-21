# OtterWorks ETL on Apache Airflow

Target-state home for the ETL jobs described in [`../ETL_UPGRADE_GUIDE.md`](../ETL_UPGRADE_GUIDE.md).
The legacy cron scripts under `../scripts/` remain in place as the before-state and are
untouched; they are decommissioned only once their Airflow equivalent is live.

## Layout

```
etl/airflow/
├── dags/                              # one module per DAG, import-light
│   └── otterworks_storage_cleanup.py  # replaces cron `30 2 * * * storage_cleanup_daily.py`
├── plugins/otterworks_etl/            # shared, importable, unit-testable job logic
│   ├── config.py                      # Airflow Variables/Connections access
│   └── storage_cleanup.py             # extract / compare / quarantine / report stages
├── tests/                             # pytest suite (DAG integrity + unit tests)
├── requirements.txt                   # runtime deps
├── requirements-dev.txt               # test/lint deps
└── constraints-2.8.4-python3.11.txt   # Airflow constraints reference
```

The stage functions in `plugins/otterworks_etl/` accept an already-built hook, so they can be
tested against moto-backed hooks or plain fakes without an Airflow scheduler.

## Migrated DAG: `otterworks_storage_cleanup`

| Legacy | Airflow |
|--------|---------|
| cron `30 2 * * *` | `schedule="30 2 * * *"`, `max_active_runs=1`, `catchup=False` |
| `config.ini` `[aws]` keys | Connection `aws_default` |
| `config.ini` `[database]` | Connection `otterworks_postgres` |
| `config.ini` `[s3]` names | Airflow Variables (see below) |
| `boto3.client("s3")` | `S3Hook(aws_conn_id="aws_default")` |
| `boto3.resource("dynamodb")` | `DynamoDBHook(aws_conn_id="aws_default")` |
| n/a (no ledger) | `PostgresHook(postgres_conn_id="otterworks_postgres")` |
| `except Exception: print(WARNING)` | task fails; 3 retries with exponential backoff (5m → 30m cap) |
| `print()` | `logging.getLogger(__name__)` |
| one `main()` | `[list_s3_objects, list_metadata_references] >> find_orphaned_objects >> move_to_quarantine >> generate_storage_report` |

### Required Airflow Variables

All non-sensitive; each has a safe default in `plugins/otterworks_etl/config.py`.

| Variable | Default |
|----------|---------|
| `otterworks_file_storage_bucket` | `otterworks-file-storage` |
| `otterworks_quarantine_bucket` | `otterworks-file-quarantine` |
| `otterworks_data_lake_bucket` | `otterworks-data-lake` |
| `otterworks_file_metadata_table` | `otterworks-file-metadata` |
| `otterworks_files_prefix` | `files/` |
| `otterworks_quarantine_prefix` | `quarantined` |
| `otterworks_quarantine_ledger_table` | `etl_storage_quarantine_ledger` |

### Required Connections

| Conn id | Type | Notes |
|---------|------|-------|
| `aws_default` | `aws` | Prefer IAM role / instance profile or a secrets backend; no keys in this repo |
| `otterworks_postgres` | `postgres` | Analytics database holding the quarantine ledger |

Set them out-of-band (Airflow UI, `airflow connections add`, or a secrets backend). No credential
is stored in version control and the DAG never reads `etl/config.ini`.

### Idempotency

Re-running the same logical date is a no-op beyond logging:

- the quarantine destination key is `quarantined/<ds>/<source key>`, derived from the logical
  date, and an object already at that key is skipped instead of re-copied;
- the source delete is a no-op when the key is already gone;
- the ledger insert is `ON CONFLICT (report_date, s3_key) DO NOTHING`;
- the report is written to the single per-date key `reports/storage-cleanup/<ds>/report.json`.

`catchup=False`: the job compares *current* bucket state against *current* metadata, so a
backfilled run for an old logical date would observe today's inventory and simply re-quarantine
under a stale prefix. Backfill adds no information and is deliberately disabled; a missed day is
absorbed by the next scheduled run.

## Local development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt -c constraints-2.8.4-python3.11.txt
.venv/bin/pip install -r requirements-dev.txt
AIRFLOW_HOME=$(mktemp -d) .venv/bin/pytest -q
.venv/bin/ruff check .
```

DAG import check (must report zero import errors):

```bash
AIRFLOW_HOME=$(mktemp -d) PYTHONPATH=plugins .venv/bin/python -c \
  "from airflow.models import DagBag; b=DagBag('dags', include_examples=False); \
   print(b.import_errors); assert not b.import_errors"
```
