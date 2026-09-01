# 08_governance_inventory.md — governance census of the legacy ETL estate

Written by `!dbx_estate_inventory`, 2026-09-01. Source is read-only; values redacted, names only.
The estate has no grants, roles, row filters, masks, or audit rules of its own: access control is
host filesystem permission on `etl/config.ini` and the crontab user. Everything below is FACT.

## Credentials and endpoints (`etl/config.ini`)

| Key | Section | Kind | Consumed by | Cite | Target |
|---|---|---|---|---|---|
| `access_key`, `secret_key`, `region` | `[aws]` | AWS static credential, plaintext | J1-J5 (`config.get("aws", ...)`) | `config.ini:3-5`; e.g. `analytics_daily.py:32-33`, `audit_archive_weekly.py:40` | retired — Databricks-side access via secret scope `ow_tp` / instance profile; AWS side `AWS_ACCESS_KEY_ID` by name |
| `host`, `port`, `database`, `user`, `password` | `[database]` | PostgreSQL credential, plaintext | J1 (`analytics_daily.py:36-40,347-352`), J5 (`user_activity_daily.py`) | `config.ini:8-12` | `ow_tp` secret scope keys `pg_*` (names only) — needed only while PG remains a coexistence consumer |
| `document_service_url`, `file_service_url`, `meilisearch_url` | `[services]` | endpoints | J3 | `config.ini:15-17`; `search_reindex_weekly.py:24-31` | job parameters |
| `meilisearch_api_key` | `[services]` | API key, plaintext, sent as `Authorization: Bearer` | J3 | `config.ini:18`; `search_reindex_weekly.py:31,39-41` | secret scope `ow_tp` key `meilisearch_api_key` |
| `data_lake_bucket`, `file_storage_bucket`, `quarantine_bucket`, `archive_bucket`, `analytics_prefix` | `[s3]` | resource names (non-secret) | J1, J2, J4, J5 | `config.ini:21-25` | job parameters / Terraform variables |
| SQS queue URL (account id embedded) | hardcoded | resource name | J1 | `analytics_daily.py:51-52` (TODO ETL-089) | job parameter |

## External principals and recipients

| Item | Value (redacted where secret) | Cite | Note |
|---|---|---|---|
| Mainframe SFTP fixture | host `127.0.0.1:52222`, user `mainframe` (uid `mvsprod`), password `<redacted>`, dir `upload/` | `docker-compose.sftp.yml:6,18,20,22` | local stand-in only; production mainframe principal unknown (D7-1) |
| Finance report recipients | `finance-reports@otterworks.dev`; `jake@otterworks.dev` (left 2020, bounces); `dev-null@localhost` fallback | `finance_excel_report.pl:18,21,24` | sendmail relay retired 2020 (`ops/RESTART_PROCEDURE.doc.txt:31`) — delivery is a no-op (D4-1) |
| Cron user | unspecified in crontab (installed per-user) | `etl/legacy-extra/crontab` | UNVERIFIABLE without host access |

## Filesystem permissions and runtime state

| Item | Evidence |
|---|---|
| `chmod`/`umask` directives in source | none in `etl/**` |
| File modes in repo | `0755` for J6-J9 and `tools/gen_*.pl`; `0775` `etl/run.sh`; `0644` Python jobs, config, crontabs; `0664` `ETL_UPGRADE_GUIDE.md` |
| Lock files, never removed | `/tmp/sftp_ingest.lock` (`sftp_ingest_poll.ksh:29-34,69`), `/tmp/parse_custbill.lock` (`parse_custbill_fixedwidth.sh:30-34`), `/tmp/finance_report.lock` (`finance_excel_report.pl:29-31`) |
| Temp files | `/tmp/cb_body.$$` (`parse_custbill_fixedwidth.sh:50-69`) |
| Working root | `$OTTERWORKS_LEGACY_ROOT` default `/tmp/otterworks-legacy`; production `/data/etl` branch by hostname (`sftp_ingest_poll.ksh:14-23`, `parse_custbill_fixedwidth.sh:25`, `finance_excel_report.pl:23`) |
| Runtime env file | `/opt/etl/.env` sourced by `etl/run.sh` — not in repo, contents unknown |

## Target governance (PROPOSED, decided at plan)

- Secret scope `ow_tp` seeded by the parent in wave 0 (D8-1); children receive secret names only.
- Unity Catalog grants: none beyond the owning principal on `ow_tp` (guardrail: no grants elsewhere).
- Lock files and `/tmp` state are not migrated; Workflows `max_concurrent_runs=1` replaces them.
- Finance distribution and mainframe principal remain customer-owned decisions (D4-1, D7-1).
