# Legacy ETL estate census

**Scope:** `etl/` and `etl/legacy-extra/` only. This is a mechanical breadth census; no conversion analysis is included. Source files under `etl/**` were read only.

**Line-citation convention:** every source claim below ends in `path:line` (ranges use `path:start-end`). LOC values were measured with `wc -l`; the cited range is the corresponding source span.

## Jobs

### 1. `etl/scripts/analytics_daily.py`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 452 LOC (`etl/scripts/analytics_daily.py:1-452`); Python 3 (`etl/scripts/analytics_daily.py:1`), originally Python 2.7 and ported in 2021 (`etl/scripts/analytics_daily.py:2-4`). Cron invokes `/opt/etl/run.sh analytics_daily.py` at `etl/legacy-extra/crontab:10`; `etl/run.sh:3-7` changes to `/opt/etl/scripts` and runs `python3 "$1"`. |
| Schedule / log | `0 2 * * *`: daily at 02:00 (`etl/legacy-extra/crontab:10`; summarized as daily 02:00 in `etl/ETL_UPGRADE_GUIDE.md:28`); stdout/stderr append to `/var/log/etl/analytics.log` (`etl/legacy-extra/crontab:10`). |
| READS | `/opt/etl/config.ini`, sections `[aws]`, `[database]`, `[s3]`, keys loaded at `etl/scripts/analytics_daily.py:28-43`; SQS queue URL `https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics`, hardcoded rather than a config key (`etl/scripts/analytics_daily.py:50-58`), messages read with `receive_message` (`etl/scripts/analytics_daily.py:68-90`); DynamoDB table `otterworks-analytics-events`, filtered by `event_date` beginning with current UTC `ds` (`etl/scripts/analytics_daily.py:111-140`); runner environment is sourced from `/opt/etl/.env` and `PYTHONPATH=/opt/etl` (`etl/run.sh:4-5`); no REST, MeiliSearch, or filesystem input paths are referenced in the job. |
| WRITES | Deletes successfully parsed SQS messages with `delete_message_batch` (`etl/scripts/analytics_daily.py:92-107`); writes gzip S3 objects to configured `data_lake_bucket` under configured `analytics_prefix` partitioned as `analytics/daily/year=YYYY/month=MM/day=DD`: `summary.json.gz`, `hourly_breakdown.json.gz`, and `top_users.jsonl.gz` (`etl/scripts/analytics_daily.py:296-338`); upserts PostgreSQL table `analytics_daily_summary` on `report_date` (`etl/scripts/analytics_daily.py:340-394`); writes JSON report `reports/analytics/daily/YYYY-MM-DD/report.json` to the configured data-lake bucket (`etl/scripts/analytics_daily.py:413-437`). |
| Consumers found | Exact output-path/table grep in `services/`, `frontend/`, `docs/`, `infrastructure/`: **none found in repo** for `reports/analytics/daily`, `analytics_daily_summary`, `summary.json.gz`, `hourly_breakdown.json.gz`, or `top_users.jsonl.gz`. The related runtime queue name is independently present at `services/analytics-service/src/main/resources/application.conf:25`, but that is not a consumer of this job's output. |
| Failure / quality smells | Bare `except` on SQS receive, retries only three consecutive failures then breaks (`etl/scripts/analytics_daily.py:68-85`); malformed SQS JSON is silently dropped (`etl/scripts/analytics_daily.py:92-105`); hardcoded queue URL and 10,000-message limit (`etl/scripts/analytics_daily.py:50-63`); timestamp parse failures silently become hour `00` (`etl/scripts/analytics_daily.py:169-180`); PostgreSQL failure is logged/rolled back but does not fail the job (`etl/scripts/analytics_daily.py:395-404`); all events are accumulated and transformed in pandas in memory (`etl/scripts/analytics_daily.py:144-154`). |
| Last-run evidence | No job log/history artifact is present in the repository; the only referenced runtime log is `/var/log/etl/analytics.log` (`etl/legacy-extra/crontab:10`). |

### 2. `etl/scripts/audit_archive_weekly.py`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 224 LOC (`etl/scripts/audit_archive_weekly.py:1-224`); Python 3 (`etl/scripts/audit_archive_weekly.py:1`), originally Python 2.7 (`etl/scripts/audit_archive_weekly.py:2-5`). Cron invokes `/opt/etl/run.sh audit_archive_weekly.py` (`etl/legacy-extra/crontab:11`; wrapper `etl/run.sh:3-7`). |
| Schedule / log | `0 3 * * 0`: Sundays at 03:00 (`etl/legacy-extra/crontab:11`; `etl/ETL_UPGRADE_GUIDE.md:29`); `/var/log/etl/audit.log` (`etl/legacy-extra/crontab:11`). |
| READS | `/opt/etl/config.ini`, `[aws]` and `[s3]` keys (`etl/scripts/audit_archive_weekly.py:36-45`); DynamoDB table `otterworks-audit-events` (`etl/scripts/audit_archive_weekly.py:46-50`, `etl/scripts/audit_archive_weekly.py:60-67`); full paginated scan filtered for `timestamp < cutoff_date`, where cutoff is 90 days before current UTC date (`etl/scripts/audit_archive_weekly.py:46-58`, `etl/scripts/audit_archive_weekly.py:69-84`); runner environment is sourced from `/opt/etl/.env` and `PYTHONPATH=/opt/etl` (`etl/run.sh:4-5`). No REST, MeiliSearch, or filesystem input path is referenced. |
| WRITES | Configured `archive_bucket`: `audit-archive/year=YYYY/week=YYYY-MM-DD/audit_events.jsonl.gz`, with S3 `StorageClass="GLACIER"` (`etl/scripts/audit_archive_weekly.py:95-125`); deletes archived DynamoDB records in batches of 25 using `event_id` and `timestamp` keys (`etl/scripts/audit_archive_weekly.py:131-169`); writes compliance JSON to configured archive bucket at `reports/compliance/audit-archive/YYYY-MM-DD/report.json` (`etl/scripts/audit_archive_weekly.py:171-216`). |
| Consumers found | Exact report/object keys have **none found in repo**. The configured archive bucket name is consumed/configured by the audit service at `services/audit-service/src/Config/AwsSettings.cs:8` and `services/audit-service/appsettings.json:11`; that service's own key format is `audit-archive/{olderThan:yyyy-MM-dd}/{Guid}.json` at `services/audit-service/src/Services/S3AuditArchiver.cs:92`, not the exact weekly-job key. The DynamoDB table is provisioned/referenced at `infrastructure/terraform/modules/database/main.tf:131`, `infrastructure/terraform/modules/database/outputs.tf:21-28`, and `infrastructure/terraform/main.tf:316-317`. |
| Failure / quality smells | Full scan is explicitly non-incremental (`etl/scripts/audit_archive_weekly.py:8`, `etl/scripts/audit_archive_weekly.py:69-84`); batch delete exceptions are swallowed and `deleted_count` can under-report without failing (`etl/scripts/audit_archive_weekly.py:146-165`); no retry/throttling handling is implemented (`etl/scripts/audit_archive_weekly.py:8-9`, `etl/scripts/audit_archive_weekly.py:146-165`); date-derived archive/report keys are reused for a run date (`etl/scripts/audit_archive_weekly.py:95-97`, `etl/scripts/audit_archive_weekly.py:171-194`). |
| Last-run evidence | No log/history artifact is present in the repository; runtime log path is `/var/log/etl/audit.log` (`etl/legacy-extra/crontab:11`). |

### 3. `etl/scripts/search_reindex_weekly.py`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 319 LOC (`etl/scripts/search_reindex_weekly.py:1-319`); Python 3 (`etl/scripts/search_reindex_weekly.py:1`), originally Python 2.7 (`etl/scripts/search_reindex_weekly.py:2-5`). Cron invokes `/opt/etl/run.sh search_reindex_weekly.py` (`etl/legacy-extra/crontab:12`; wrapper `etl/run.sh:3-7`). |
| Schedule / log | `0 4 * * 0`: Sundays at 04:00 (`etl/legacy-extra/crontab:12`; `etl/ETL_UPGRADE_GUIDE.md:30`); `/var/log/etl/search.log` (`etl/legacy-extra/crontab:12`). |
| READS | `/opt/etl/config.ini`, `[services]` keys `document_service_url`, `file_service_url`, `meilisearch_url`, `meilisearch_api_key` (`etl/scripts/search_reindex_weekly.py:24-31`); document REST endpoint `${document_service_url}/api/v1/documents`, paginated with `page` and `size` (`etl/scripts/search_reindex_weekly.py:150-167`); file REST endpoint `${file_service_url}/api/v1/files`, paginated with `page` and `page_size` (`etl/scripts/search_reindex_weekly.py:213-229`); MeiliSearch task/status and stats endpoints under configured `meilisearch_url` (`etl/scripts/search_reindex_weekly.py:45-68`, `etl/scripts/search_reindex_weekly.py:84-94`, `etl/scripts/search_reindex_weekly.py:280-292`); runner environment is sourced from `/opt/etl/.env` and `PYTHONPATH=/opt/etl` (`etl/run.sh:4-5`). No S3, PostgreSQL, or filesystem input path is referenced. |
| WRITES | Deletes existing MeiliSearch indexes `documents` and `files` (`etl/scripts/search_reindex_weekly.py:42-72`); creates those indexes with primary key `id` (`etl/scripts/search_reindex_weekly.py:73-94`); patches their settings (`etl/scripts/search_reindex_weekly.py:96-148`); bulk-writes document records to `documents` (`etl/scripts/search_reindex_weekly.py:169-211`) and file records to `files` (`etl/scripts/search_reindex_weekly.py:231-275`); reads index stats to validate counts (`etl/scripts/search_reindex_weekly.py:277-309`). |
| Consumers found | Search service configuration defaults the same index names through `MEILISEARCH_DOCUMENTS_INDEX`/`MEILISEARCH_FILES_INDEX` (`services/search-service/app/config.py:8-17`) and uses the shared MeiliSearch service (`services/search-service/app/main.py:64-78`, `services/search-service/app/api/search.py:39-40`). Its document/file indexing API is at `services/search-service/app/api/index.py:25-35` and `services/search-service/app/api/index.py:45-55`; indexer writes are at `services/search-service/app/services/indexer.py:19-24`, `services/search-service/app/services/indexer.py:46-48`, and `services/search-service/app/services/indexer.py:73-75`. Source REST routes are documented at `docs/api-route-matrix.md:10`, `docs/api-route-matrix.md:24-28`. |
| Failure / quality smells | Bare exception treats missing indexes as normal (`etl/scripts/search_reindex_weekly.py:42-72`); no session reuse, timeout, or retry is explicitly noted (`etl/scripts/search_reindex_weekly.py:156-162`); task polling uses fixed sleeps and deadlines (`etl/scripts/search_reindex_weekly.py:54-68`, `etl/scripts/search_reindex_weekly.py:83-94`, `etl/scripts/search_reindex_weekly.py:109-120`, `etl/scripts/search_reindex_weekly.py:135-146`, `etl/scripts/search_reindex_weekly.py:188-204`, `etl/scripts/search_reindex_weekly.py:252-268`); failed indexing is warned before count validation (`etl/scripts/search_reindex_weekly.py:197-204`). |
| Last-run evidence | No job log/history artifact is present in the repository; runtime log path is `/var/log/etl/search.log` (`etl/legacy-extra/crontab:12`). |

### 4. `etl/scripts/storage_cleanup_daily.py`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 217 LOC (`etl/scripts/storage_cleanup_daily.py:1-217`); Python 3 (`etl/scripts/storage_cleanup_daily.py:1`), originally Python 2.7 (`etl/scripts/storage_cleanup_daily.py:2-5`). Cron invokes `/opt/etl/run.sh storage_cleanup_daily.py` (`etl/legacy-extra/crontab:13`; wrapper `etl/run.sh:3-7`). |
| Schedule / log | `30 2 * * *`: daily at 02:30 (`etl/legacy-extra/crontab:13`; `etl/ETL_UPGRADE_GUIDE.md:31`); `/var/log/etl/storage.log` (`etl/legacy-extra/crontab:13`). |
| READS | `/opt/etl/config.ini`, `[aws]` and `[s3]` keys (`etl/scripts/storage_cleanup_daily.py:23-37`); S3 configured `file_storage_bucket`, prefix `files/` (`etl/scripts/storage_cleanup_daily.py:31-36`, `etl/scripts/storage_cleanup_daily.py:41-62`); DynamoDB table `otterworks-file-metadata`, scanning `s3_key` references (`etl/scripts/storage_cleanup_daily.py:35-37`, `etl/scripts/storage_cleanup_daily.py:71-99`); runner environment is sourced from `/opt/etl/.env` and `PYTHONPATH=/opt/etl` (`etl/run.sh:4-5`). No REST, PostgreSQL, MeiliSearch, or local filesystem input is referenced. |
| WRITES | For each unreferenced S3 object, copies from configured file-storage bucket/key to configured quarantine bucket at `quarantined/YYYY-MM-DD/<source_key>` and then deletes the source object (`etl/scripts/storage_cleanup_daily.py:105-151`); writes JSON report to configured data-lake bucket at `reports/storage-cleanup/YYYY-MM-DD/report.json` (`etl/scripts/storage_cleanup_daily.py:160-209`). |
| Consumers found | Exact `reports/storage-cleanup` output and `quarantined` prefix: **none found in repo**. Metadata table name is referenced by the file service at `services/file-service/src/config.rs:64` and documented at `docs/tech-partnerships/runbook-mongodb.md:33`, `docs/tech-partnerships/runbook-mongodb.md:119`, and `docs/tech-partnerships/runbook-mongodb.md:149`. |
| Failure / quality smells | No dry-run mode is implemented (`etl/scripts/storage_cleanup_daily.py:8-10`); hardcoded `files/`, `quarantined`, and `otterworks-file-metadata` names (`etl/scripts/storage_cleanup_daily.py:31-37`); each copy/delete is destructive after copy and catches failures per object (`etl/scripts/storage_cleanup_daily.py:134-151`); no retention/lifecycle handling is visible, and the addendum records archive growth/absence of purge (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:59-60`). |
| Last-run evidence | No job log/history artifact is present in the repository; runtime log path is `/var/log/etl/storage.log` (`etl/legacy-extra/crontab:13`). |

### 5. `etl/scripts/user_activity_daily.py`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 255 LOC (`etl/scripts/user_activity_daily.py:1-255`); Python 3 (`etl/scripts/user_activity_daily.py:1`), originally Python 2.7 (`etl/scripts/user_activity_daily.py:2-5`). Cron invokes `/opt/etl/run.sh user_activity_daily.py` (`etl/legacy-extra/crontab:14`; wrapper `etl/run.sh:3-7`). |
| Schedule / log | `0 5 * * *`: daily at 05:00 (`etl/legacy-extra/crontab:14`; `etl/ETL_UPGRADE_GUIDE.md:32`); `/var/log/etl/activity.log` (`etl/legacy-extra/crontab:14`). |
| READS | `/opt/etl/config.ini`, `[aws]` and `[database]` keys (`etl/scripts/user_activity_daily.py:25-40`); PostgreSQL query reads `analytics_daily_summary` for a 30-day date interval (`etl/scripts/user_activity_daily.py:41-43`, `etl/scripts/user_activity_daily.py:64-84`); configured data-lake bucket (`etl/scripts/user_activity_daily.py:39-43`); reads `analytics/daily/year=YYYY/month=MM/day=DD/top_users.jsonl.gz` for each lookback day (`etl/scripts/user_activity_daily.py:124-147`); runner environment is sourced from `/opt/etl/.env` and `PYTHONPATH=/opt/etl` (`etl/run.sh:4-5`). No REST or MeiliSearch input is referenced. |
| WRITES | Writes full report to configured data-lake bucket at `reports/user-activity/YYYY-MM-DD/activity_report.json` (`etl/scripts/user_activity_daily.py:204-220`); writes latest pointer `reports/user-activity/latest/activity_report.json` (`etl/scripts/user_activity_daily.py:222-228`); conditionally writes per-user JSONL `reports/user-activity/YYYY-MM-DD/user_summaries.jsonl` (`etl/scripts/user_activity_daily.py:230-239`). |
| Consumers found | Exact `reports/user-activity`, `user_summaries.jsonl`, and `analytics/daily/year` output paths: **none found in repo**. `activity_report.json` is named as an admin-service output whose path/shape is intended to remain compatible at `docs/tech-partnerships/OtterWorks_ETL_target_state.md:98`; no concrete admin-service reader for this exact path was found. |
| Failure / quality smells | PostgreSQL query failure exits immediately (`etl/scripts/user_activity_daily.py:113-117`); missing/unreadable S3 daily objects are silently skipped by bare `except` (`etl/scripts/user_activity_daily.py:139-176`); 30-day lookback and report prefix are hardcoded (`etl/scripts/user_activity_daily.py:41-43`); no retry logic is visible around PostgreSQL or S3 operations (`etl/scripts/user_activity_daily.py:54-84`, `etl/scripts/user_activity_daily.py:129-176`). |
| Last-run evidence | No job log/history artifact is present in the repository; runtime log path is `/var/log/etl/activity.log` (`etl/legacy-extra/crontab:14`). |

### 6. `etl/legacy-extra/jobs/sftp_ingest_poll.ksh`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 70 LOC (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:1-70`); KornShell (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:1`), 1998 origin/2014 Linux port (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:5-10`). Cron directly invokes it (`etl/legacy-extra/crontab:20`); `run_all.sh` invokes it first (`etl/legacy-extra/run_all.sh:14-20`). |
| Schedule / log | `*/15 * * * *`: every 15 minutes (`etl/legacy-extra/crontab:17-20`); `/var/log/etl/sftp_ingest.log` (`etl/legacy-extra/crontab:20`). |
| READS | Hostname and `OTTERWORKS_LEGACY_ROOT` determine root/drop paths (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:14-24`); polls filesystem `$SFTP_DROP/CUSTBILL*.dat` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:45-49`); reads file sizes twice with `wc -c` one second apart (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:50-56`). Prod input is `/sftp/mainframe/upload`, UAT input `/sftp_uat/mainframe/upload`, fallback input `$OTTERWORKS_LEGACY_ROOT/sftp-drop/upload` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:15-24`). |
| WRITES | Creates `$ROOT/incoming`, `$ROOT/archive`, and drop directories (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:27-38`); copies each settled source file to `$ROOT/incoming/<basename>` and timestamped `$ROOT/archive/<basename>.<YYYYMMDDHHMMSS>` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:58-59`); deletes the source from the drop (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:60`); creates/retains `/tmp/sftp_ingest.lock` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:27-36`, `etl/legacy-extra/jobs/sftp_ingest_poll.ksh:69`). |
| Consumers found | Exact `incoming/`, `archive/`, and CUSTBILL path consumers are the parser's input loop (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:28-45`) and the runbook's bronze mapping (`docs/tech-partnerships/runbook-databricks.md:104-107`). No consumer outside the estate was found for the timestamped archive path. |
| Failure / quality smells | Lock is checked but ignored and never removed (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:31-36`, `etl/legacy-extra/jobs/sftp_ingest_poll.ksh:69`); size-twice/one-second settle hack has no atomic rename or transfer manifest (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:42-56`); `cp`, `rm`, directory creation, and size checks suppress errors with `2>/dev/null || true` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:36-38`, `etl/legacy-extra/jobs/sftp_ingest_poll.ksh:50-60`); fixed hostname branches and hardcoded production paths (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:14-24`); polling sleeps are timing dependencies (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:45-65`). |
| Last-run evidence | No log/history artifact is present in the repository; runtime log path is `/var/log/etl/sftp_ingest.log` (`etl/legacy-extra/crontab:20`). |

### 7. `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 81 LOC (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:1-81`); bash plus `sed`, `cut`, `paste`, and `awk` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:1`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:47-67`). Cron directly invokes it (`etl/legacy-extra/crontab:24`); `run_all.sh` invokes it second (`etl/legacy-extra/run_all.sh:22-23`). |
| Schedule / log | `5-59/15 * * * *`: at :05, :20, :35, :50 every hour (`etl/legacy-extra/crontab:22-24`); `/var/log/etl/parse.log` (`etl/legacy-extra/crontab:24`). |
| READS | Hostname and `OTTERWORKS_LEGACY_ROOT` determine root (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:20-26`); filesystem `$ROOT/incoming/CUSTBILL*.dat` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:28-45`); fixed-width field positions 1-65 are documented in the header (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:5-14`); reads `HDR`/`TRL` records for filtering/count logging (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:47-50`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:71-75`). |
| WRITES | Creates `/tmp/parse_custbill.lock` and `$ROOT/parsed` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:28-38`); creates intermediate `/tmp/cb_body.$$` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:47-50`); writes `$ROOT/parsed/<basename>.psv`, pipe-delimited six fields with trimmed name/currency, two-decimal amount and reformatted date (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:42-67`); deletes the temporary body on the normal path (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:69`); renames incoming `.dat` to `.dat.done` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:77`); leaves lock file in place (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:30-36`). |
| Consumers found | `finance_excel_report.pl` reads `parsed/CUSTBILL*.psv` (`etl/legacy-extra/jobs/finance_excel_report.pl:41-55`); runbook defines `.psv` as the silver input/baseline (`docs/tech-partnerships/runbook-databricks.md:107`, `docs/tech-partnerships/runbook-databricks.md:141-149`); no additional `services/`, `frontend/`, or `infrastructure/` consumer was found for `.psv`. |
| Failure / quality smells | Header states no validation and bad records pass through (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:16-18`); fixed-width conversion is three `cut` passes plus `sed`/`awk` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:47-67`); date validity is not checked and amount is coerced with awk (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:60-67`); parser output errors and moves are suppressed with `2>/dev/null || true` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:50-67`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:69`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:77`); trailer count is logged but not reconciled (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:71-75`); lock is never removed (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:30-36`). |
| Last-run evidence | No log/history artifact is present in the repository; runtime log path is `/var/log/etl/parse.log` (`etl/legacy-extra/crontab:24`). |

### 8. `etl/legacy-extra/jobs/finance_excel_report.pl`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 91 LOC (`etl/legacy-extra/jobs/finance_excel_report.pl:1-91`); Perl, no modules, Perl 5.005 heritage (`etl/legacy-extra/jobs/finance_excel_report.pl:1-12`). Cron directly invokes it (`etl/legacy-extra/crontab:28`); `run_all.sh` invokes it third (`etl/legacy-extra/run_all.sh:25`). |
| Schedule / log | `10 2 * * *`: daily at 02:10 (`etl/legacy-extra/crontab:26-28`; addendum `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:14-17`); `/var/log/etl/finance.log` (`etl/legacy-extra/crontab:28`). |
| READS | Hostname and `OTTERWORKS_LEGACY_ROOT` determine root; hostname also selects recipient (`etl/legacy-extra/jobs/finance_excel_report.pl:15-25`); `$ROOT/parsed/CUSTBILL*.psv` (`etl/legacy-extra/jobs/finance_excel_report.pl:27-29`, `etl/legacy-extra/jobs/finance_excel_report.pl:41-55`); optional `/usr/sbin/sendmail` executable and pipe (`etl/legacy-extra/jobs/finance_excel_report.pl:79-87`). |
| WRITES | Creates `/tmp/finance_report.lock` (`etl/legacy-extra/jobs/finance_excel_report.pl:27-35`); creates `$ROOT/parsed` and `$ROOT/reports` (`etl/legacy-extra/jobs/finance_excel_report.pl:27-37`); writes `$ROOT/reports/finance_billing_YYYYMMDD.csv` with currency/record-type totals (`etl/legacy-extra/jobs/finance_excel_report.pl:60-72`); copies CSV to `$ROOT/reports/finance_billing_YYYYMMDD.xls` (`etl/legacy-extra/jobs/finance_excel_report.pl:74-77`); conditionally writes an email through sendmail (`etl/legacy-extra/jobs/finance_excel_report.pl:79-87`); lock is not removed (`etl/legacy-extra/jobs/finance_excel_report.pl:29-35`). |
| Consumers found | Exact `finance_billing_` output has no consumer outside the estate; runbook instructs operators to read the CSV and cites the `.xls` output (`docs/tech-partnerships/runbook-databricks.md:77`, `docs/tech-partnerships/runbook-databricks.md:81-98`); addendum documents `reports/finance_billing_*.{csv,xls}` (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:38-40`). |
| Failure / quality smells | CSV is copied/renamed as `.xls`, not converted to an Excel workbook (`etl/legacy-extra/jobs/finance_excel_report.pl:5-9`, `etl/legacy-extra/jobs/finance_excel_report.pl:74-75`); unreadable parsed files are skipped (`etl/legacy-extra/jobs/finance_excel_report.pl:47-55`); sendmail delivery silently no-ops if unavailable and stderr is suppressed (`etl/legacy-extra/jobs/finance_excel_report.pl:79-87`); no `use strict` and no modules (`etl/legacy-extra/jobs/finance_excel_report.pl:11-12`); lock is never removed (`etl/legacy-extra/jobs/finance_excel_report.pl:29-35`); hostname-selected hardcoded roots and recipients (`etl/legacy-extra/jobs/finance_excel_report.pl:15-25`). |
| Last-run evidence | No log/history artifact is present in the repository; runtime log path is `/var/log/etl/finance.log` (`etl/legacy-extra/crontab:28`). |

### 9. `etl/legacy-extra/run_all.sh`

| Field | Census |
|---|---|
| LOC / runtime / entrypoint | 28 LOC (`etl/legacy-extra/run_all.sh:1-28`); bash (`etl/legacy-extra/run_all.sh:1`). Cron invokes it Sundays at 06:00 (`etl/legacy-extra/crontab:30-32`). |
| Schedule / log | `0 6 * * 0`: Sundays at 06:00 (`etl/legacy-extra/crontab:30-32`); `/var/log/etl/run_all.log` (`etl/legacy-extra/crontab:32`). |
| READS | The `DIR=\`dirname $0\`` assignment identifies the script directory and `RUN_ALL_SLEEP` defaults to 600 seconds (`etl/legacy-extra/run_all.sh:14-17`); reads/executes the three child scripts from `$DIR/jobs` (`etl/legacy-extra/run_all.sh:19-25`). |
| WRITES | Child side effects are the ingest, parser, and finance outputs cited above (`etl/legacy-extra/run_all.sh:19-25`); writes orchestration stdout/stderr through the cron log path (`etl/legacy-extra/crontab:32`). It does not itself create a data file. |
| Consumers found | No consumer of `run_all.sh` output beyond its crontab entry and operator documentation (`etl/legacy-extra/crontab:30-32`, `etl/legacy-extra/ops/RESTART_PROCEDURE.doc.txt:34-37`). |
| Failure / quality smells | Dependency management is `sleep 600` between stages (`etl/legacy-extra/run_all.sh:5-11`, `etl/legacy-extra/run_all.sh:19-23`); each child invocation suppresses stderr and ignores failure with `2>/dev/null || true` (`etl/legacy-extra/run_all.sh:19-25`); always exits 0 and says `run_all done (probably)` (`etl/legacy-extra/run_all.sh:27-28`); child jobs have their own never-removed locks (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:31-36`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:30-36`, `etl/legacy-extra/jobs/finance_excel_report.pl:29-35`). |
| Last-run evidence | No log/history artifact is present in the repository; runtime log path is `/var/log/etl/run_all.log` (`etl/legacy-extra/crontab:32`). |

## Scheduler edges

### Full `etl/legacy-extra/crontab` table

| Job | Cron expression | Calendar meaning | Log | Concurrent/overlap evidence |
|---|---|---|---|---|
| analytics_daily.py | `0 2 * * *` | Daily 02:00 | `/var/log/etl/analytics.log` | Finance starts at 02:10; crontab explicitly says it overlaps analytics (`etl/legacy-extra/crontab:10`, `etl/legacy-extra/crontab:26-28`). |
| audit_archive_weekly.py | `0 3 * * 0` | Sunday 03:00 | `/var/log/etl/audit.log` | No exact same-minute entry; may overlap long-running jobs because there is no cross-job lock (`etl/legacy-extra/crontab:5-7`, `etl/legacy-extra/crontab:11`). |
| search_reindex_weekly.py | `0 4 * * 0` | Sunday 04:00 | `/var/log/etl/search.log` | No exact same-minute entry; no cross-job lock (`etl/legacy-extra/crontab:5-7`, `etl/legacy-extra/crontab:12`). |
| storage_cleanup_daily.py | `30 2 * * *` | Daily 02:30 | `/var/log/etl/storage.log` | Runs in the same 02:00 hour as analytics and finance; no cross-job lock (`etl/legacy-extra/crontab:5-7`, `etl/legacy-extra/crontab:13`). |
| user_activity_daily.py | `0 5 * * *` | Daily 05:00 | `/var/log/etl/activity.log` | No exact same-minute entry; no cross-job lock (`etl/legacy-extra/crontab:5-7`, `etl/legacy-extra/crontab:14`). |
| sftp_ingest_poll.ksh | `*/15 * * * *` | Every hour at :00, :15, :30, :45 | `/var/log/etl/sftp_ingest.log` | A run can take about 7 minutes; the crontab says the next :15 run can overlap the :00 run (`etl/legacy-extra/crontab:16-20`). |
| parse_custbill_fixedwidth.sh | `5-59/15 * * * *` | Every hour at :05, :20, :35, :50 | `/var/log/etl/parse.log` | Offset from ingest by 5 minutes; crontab says parse can start while ingest copies and read a half-written file (`etl/legacy-extra/crontab:22-24`). |
| finance_excel_report.pl | `10 2 * * *` | Daily 02:10 | `/var/log/etl/finance.log` | Explicitly overlaps analytics at 02:00 (`etl/legacy-extra/crontab:26-28`). |
| run_all.sh | `0 6 * * 0` | Sunday 06:00 | `/var/log/etl/run_all.log` | Explicitly described as overlapping all above on Sundays (`etl/legacy-extra/crontab:30-32`). |

### Minute-level overlap analysis

- Ingest starts at every `:00/:15/:30/:45`; parser starts five minutes later at `:05/:20/:35/:50`. The crontab records the ingest duration as approximately seven minutes, so each parser start can overlap the preceding ingest window (`etl/legacy-extra/crontab:16-24`).
- Finance at 02:10 starts ten minutes after analytics at 02:00 and is explicitly documented as overlapping it (`etl/legacy-extra/crontab:26-28`). Storage starts at 02:30, while the 02:10 finance run and the 02:15 ingest/02:20 parser pair may still be running; no duration guarantee or cross-job lock is present (`etl/legacy-extra/crontab:5-7`, `etl/legacy-extra/crontab:13`, `etl/legacy-extra/crontab:20`, `etl/legacy-extra/crontab:24`, `etl/legacy-extra/crontab:28`).
- On Sunday, the 03:00 audit, 04:00 search, and 06:00 run_all entries coexist with the recurring ingest/parser and daily finance/storage/activity schedules; the crontab explicitly warns that run_all overlaps the other entries (`etl/legacy-extra/crontab:30-32`).

### `run_all.sh` call order and sleeps

1. `sftp_ingest_poll.ksh` (`etl/legacy-extra/run_all.sh:19`)
2. `sleep $SLEEP`, default `600` seconds (`etl/legacy-extra/run_all.sh:15`, `etl/legacy-extra/run_all.sh:20`)
3. `parse_custbill_fixedwidth.sh` (`etl/legacy-extra/run_all.sh:22`)
4. `sleep $SLEEP`, default `600` seconds (`etl/legacy-extra/run_all.sh:23`)
5. `finance_excel_report.pl` (`etl/legacy-extra/run_all.sh:25`)

## Data lineage edges

- `SQS otterworks-analytics` -> `all_sqs_events` -> analytics aggregation -> S3 analytics partition / PostgreSQL `analytics_daily_summary` / daily report (**FACT**; source read `etl/scripts/analytics_daily.py:50-109`, aggregation `etl/scripts/analytics_daily.py:144-294`, writes `etl/scripts/analytics_daily.py:304-394`, `etl/scripts/analytics_daily.py:413-437`).
- `DynamoDB otterworks-analytics-events` -> `all_dynamo_events` -> analytics aggregation -> same outputs (**FACT**; read `etl/scripts/analytics_daily.py:111-146`, writes `etl/scripts/analytics_daily.py:304-394`, `etl/scripts/analytics_daily.py:413-437`).
- `analytics_daily.py` -> `analytics/daily/.../top_users.jsonl.gz` -> `user_activity_daily.py` (**FACT**; producer `etl/scripts/analytics_daily.py:325-336`, consumer `etl/scripts/user_activity_daily.py:139-171`).
- `analytics_daily.py` -> PostgreSQL `analytics_daily_summary` -> `user_activity_daily.py` (**FACT**; producer upsert `etl/scripts/analytics_daily.py:355-394`, consumer query `etl/scripts/user_activity_daily.py:64-84`).
- `SFTP drop CUSTBILL*.dat` -> `$ROOT/incoming/<file>` -> `parse_custbill_fixedwidth.sh` (**FACT**; ingest copy `etl/legacy-extra/jobs/sftp_ingest_poll.ksh:47-60`, parser input `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:28-45`).
- `parse_custbill_fixedwidth.sh` -> `parsed/CUSTBILL*.psv` -> `finance_excel_report.pl` (**FACT**; producer `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:42-67`, consumer `etl/legacy-extra/jobs/finance_excel_report.pl:41-55`).
- `parse_custbill_fixedwidth.sh` -> `incoming/<file>.done` -> no downstream reader found (**FACT** for rename `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:77`; no reader was found by repo grep). 
- `DynamoDB otterworks-audit-events` -> `s3://<archive_bucket>/audit-archive/year=YYYY/week=YYYY-MM-DD/audit_events.jsonl.gz` -> no exact object consumer found (**FACT**; read/delete `etl/scripts/audit_archive_weekly.py:60-84`, write `etl/scripts/audit_archive_weekly.py:95-125`).
- `document-service /api/v1/documents` -> MeiliSearch `documents` -> search service (**FACT** for job fetch/write `etl/scripts/search_reindex_weekly.py:150-211`; repo-side search-service use `services/search-service/app/config.py:8-17`, `services/search-service/app/services/indexer.py:19-48`).
- `file-service /api/v1/files` -> MeiliSearch `files` -> search service (**FACT** for job fetch/write `etl/scripts/search_reindex_weekly.py:213-275`; repo-side search-service use `services/search-service/app/config.py:8-17`, `services/search-service/app/services/indexer.py:50-75`).
- `S3 configured file-storage bucket/files/` -> unreferenced object set -> quarantine bucket `quarantined/YYYY-MM-DD/...` and source delete (**FACT**; source enumeration `etl/scripts/storage_cleanup_daily.py:41-62`, reference comparison `etl/scripts/storage_cleanup_daily.py:71-114`, copy/delete `etl/scripts/storage_cleanup_daily.py:134-151`).
- `user_activity_daily.py` -> `reports/user-activity/.../activity_report.json` -> admin-service (**INFERRED**; the job writes that path `etl/scripts/user_activity_daily.py:204-228`, and the target-state document calls it an admin-service artifact `docs/tech-partnerships/OtterWorks_ETL_target_state.md:98`; no concrete reader was found).
- `finance_excel_report.pl` -> `reports/finance_billing_*.csv/.xls` -> finance operators/runbook (**FACT** for producer `etl/legacy-extra/jobs/finance_excel_report.pl:60-77`; runbook explicitly instructs operators to display those outputs `docs/tech-partnerships/runbook-databricks.md:81-98`).

## Governance census

### `etl/config.ini` keys (values intentionally omitted)

- `[aws]`: `access_key`, `secret_key`, `region` (`etl/config.ini:2-5`).
- `[database]`: `host`, `port`, `database`, `user`, `password` (`etl/config.ini:7-12`).
- `[services]`: `document_service_url`, `file_service_url`, `meilisearch_url`, `meilisearch_api_key` (`etl/config.ini:14-18`).
- `[s3]`: `data_lake_bucket`, `file_storage_bucket`, `quarantine_bucket`, `archive_bucket`, `analytics_prefix` (`etl/config.ini:20-25`).

### Credentials/secrets/endpoints in scripts

- Python jobs load `aws_access_key`, `aws_secret_key`, and `db_password` from config (`etl/scripts/analytics_daily.py:32-40`, `etl/scripts/audit_archive_weekly.py:40-45`, `etl/scripts/storage_cleanup_daily.py:27-33`, `etl/scripts/user_activity_daily.py:29-40`) and pass them to boto3/psycopg2 (`etl/scripts/analytics_daily.py:53-58`, `etl/scripts/analytics_daily.py:346-352`, `etl/scripts/user_activity_daily.py:55-61`). Values are not reproduced here.
- Search job loads `meilisearch_api_key` into an Authorization header (`etl/scripts/search_reindex_weekly.py:28-40`). Value is not reproduced.
- Analytics has a hardcoded SQS endpoint/queue URL (`etl/scripts/analytics_daily.py:51-57`).
- Legacy shell/Perl jobs contain no database/cloud token variables; they use filesystem roots, hostname branches, `OTTERWORKS_LEGACY_ROOT`, and sendmail recipients (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:14-24`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:20-26`, `etl/legacy-extra/jobs/finance_excel_report.pl:15-25`).
- SFTP fixture host/user: host `127.0.0.1`, port `52222`, user `mainframe`; password is present in the fixture but **redacted** here (`etl/legacy-extra/docker-compose.sftp.yml:5-7`, `etl/legacy-extra/docker-compose.sftp.yml:18-20`).
- Finance email distribution: `finance-reports@otterworks.dev`, `jake@otterworks.dev`, and fallback `dev-null@localhost` (`etl/legacy-extra/jobs/finance_excel_report.pl:15-25`).

### Permissions and process controls

- No `chmod` or `umask` directive is present in the ETL source tree (search found no such source lines).
- Observed filesystem modes: Python scripts and config/crontab are mostly `0644`; legacy jobs, `run_all.sh`, and `gen_sample_data.pl` are `0755`; `etl/run.sh` is `0775`; `etl/ETL_UPGRADE_GUIDE.md` is `0664`. This was collected with `find etl -type f -printf '%M %u:%g %p\\n'` and is filesystem metadata, not a source line.
- Runtime lock paths are `/tmp/sftp_ingest.lock`, `/tmp/parse_custbill.lock`, and `/tmp/finance_report.lock` (`etl/legacy-extra/jobs/sftp_ingest_poll.ksh:27-36`, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:28-36`, `etl/legacy-extra/jobs/finance_excel_report.pl:27-35`). Temporary parser body is `/tmp/cb_body.$$` (`etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh:50-69`).

## Support objects

| Object | Mechanical description and jobs using it |
|---|---|
| `etl/run.sh` | Bash Python launcher: sources `/opt/etl/.env`, sets `PYTHONPATH`, changes directory, runs `python3`; used by the five Python jobs (`etl/run.sh:1-7`, `etl/legacy-extra/crontab:9-14`). |
| `etl/config.ini` | Shared AWS/database/service/S3 configuration; read by all five Python jobs (`etl/config.ini:2-25`, `etl/scripts/analytics_daily.py:28-43`, `etl/scripts/audit_archive_weekly.py:36-45`, `etl/scripts/search_reindex_weekly.py:24-31`, `etl/scripts/storage_cleanup_daily.py:23-37`, `etl/scripts/user_activity_daily.py:25-40`). |
| `etl/crontab` | Five Python cron entries, duplicate of the Python section in the legacy-extra crontab (`etl/crontab:1-7`, `etl/legacy-extra/crontab:9-14`). |
| `etl/legacy-extra/crontab` | Full nine-entry estate scheduler: five Python jobs, three CUSTBILL jobs, and run_all (`etl/legacy-extra/crontab:9-32`). |
| `etl/requirements.txt` | Pinned Python dependencies: boto3, psycopg2-binary, pandas, requests (`etl/requirements.txt:1-4`); used by the Python job runtime as the dependency manifest. |
| `etl/legacy-extra/docker-compose.sftp.yml` | Optional localhost-only `atmoz/sftp` fixture, maps host `$OTTERWORKS_LEGACY_ROOT/sftp-drop/upload` to the SFTP upload directory; supports `sftp_ingest_poll.ksh` (`etl/legacy-extra/docker-compose.sftp.yml:1-22`, `etl/legacy-extra/jobs/sftp_ingest_poll.ksh:22-24`). |
| `etl/legacy-extra/tools/gen_sample_data.pl` | Deterministic CUSTBILL generator; writes the ingest drop selected by `OTTERWORKS_LEGACY_ROOT`; supports ingest/parser/finance local runs (`etl/legacy-extra/tools/gen_sample_data.pl:3-14`, `etl/legacy-extra/tools/gen_sample_data.pl:19-25`, `etl/legacy-extra/tools/gen_sample_data.pl:43-64`). |
| `etl/legacy-extra/tools/gen_history_data.pl` | Deterministic monthly historical CUSTBILL generator; writes `sftp-drop/history/<YYYY>/` and expectation manifest; local/backfill support, not part of the batch chain (`etl/legacy-extra/tools/gen_history_data.pl:3-27`, `etl/legacy-extra/tools/gen_history_data.pl:43-46`, `etl/legacy-extra/tools/gen_history_data.pl:154-197`). |
| `etl/legacy-extra/ops/RESTART_PROCEDURE.doc.txt` | Operator restart/runbook for ingest, parser, finance, Sunday run_all, temp files, and archive capacity; supports all three CUSTBILL jobs and run_all (`etl/legacy-extra/ops/RESTART_PROCEDURE.doc.txt:10-46`). |
| `etl/ETL_UPGRADE_GUIDE.md` | Main guide documenting the five Python jobs, schedules, sources/stores, cron/log posture, and script-to-DAG mapping (`etl/ETL_UPGRADE_GUIDE.md:5-32`, `etl/ETL_UPGRADE_GUIDE.md:181-187`). |
| `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md` | Addendum inventory for the three CUSTBILL jobs and run_all, output paths, local commands, and deficiency list (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:10-22`, `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:29-40`, `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:42-61`). |

## Expected-output cross-references

- `docs/tech-partnerships/runbook-databricks.md` expects two 50-record CUSTBILL files (`docs/tech-partnerships/runbook-databricks.md:20-24`), two 50-row parses and a finance `.xls` (`docs/tech-partnerships/runbook-databricks.md:70-79`), 100 parsed rows (`docs/tech-partnerships/runbook-databricks.md:81-85`), and the six currency/record-type report rows (`docs/tech-partnerships/runbook-databricks.md:88-98`).
- `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md` expects `incoming/`, `parsed/*.psv`, and `reports/finance_billing_*.{csv,xls}` (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:38-40`), and describes the three legacy job schedules/outputs (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:12-17`).

## Cross-check counts

- Cron entries: **9** in `etl/legacy-extra/crontab:10-14`, `etl/legacy-extra/crontab:20`, `etl/legacy-extra/crontab:24`, `etl/legacy-extra/crontab:28`, and `etl/legacy-extra/crontab:32`.
- Enumerated jobs: **9**: five Python jobs, three CUSTBILL jobs, and `run_all.sh` (`etl/legacy-extra/crontab:9-32`). Counts match: **9 cron entries / 9 jobs**.
- Script files (`*.py`, `*.sh`, `*.ksh`, `*.pl`): **12**. The nine jobs plus three non-job scripts: `etl/run.sh`, `etl/legacy-extra/tools/gen_sample_data.pl`, and `etl/legacy-extra/tools/gen_history_data.pl`.
- Files under `etl/` at census time: **20**, exactly the nine jobs plus the eleven requested support objects. **Anything under `etl/` not in the supplied list: none found.**
- Last-run log/history artifacts in repo: **none found**; referenced logs are host paths under `/var/log/etl/` in `etl/crontab:3-7` and `etl/legacy-extra/crontab:10-32`.
