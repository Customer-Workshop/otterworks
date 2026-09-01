# 04_dependency_register.md — dependency register

Taxonomy (playbook 13): D1 intra-pipeline lineage · D2 shared object (2+ pipelines) · D3 upstream feed ·
D4 downstream consumer · D5 scheduler · D6 shared table with non-migrated writers · D7 external hand-off ·
D8 governance/security · D9 ML/scoring consumer (N/A here; D9-1/D9-2 below predate this header and record
setup decisions) · D10 environment/access.
Status: OPEN · IN_PROGRESS · CLOSED · DEFERRED(condition). Rows are appended, never deleted.

| ID | Class | Unit(s) | Contract / description | Owner | Status | Fired request / evidence |
|---|---|---|---|---|---|---|
| D10-1 | env | all | Catalog `ow_tp` absent; preflight 3/10 DENIED (`files-get-directory`, `files-put-get`, `uc-create-list`) | parent | OPEN | Wave-0 parent task: create catalog/schemas/volume via shared Terraform, rerun `make tp-preflight PLATFORM=databricks` to clean manifest. See `07_access_checklist.md` A2. |
| D10-2 | env | all | `infrastructure/terraform-databricks/`, `scripts/tp_databricks/dbx.py`, and the 9 contract files referenced by `contracts/README.md` are absent | parent | OPEN | Wave 0 authors them; `make tp-validate-contracts` fails until then. |
| D10-3 | env | 6,7,8,9 | Legacy runtime prerequisites (`ksh`, docker+`sshpass` for SFTP fixture; LocalStack for Python jobs) | parent | CLOSED | `07_access_checklist.md` A5/A6 WORKS. |
| D5-1 | scheduler | 6,7 | `*/15` ingest vs `5-59/15` parse: half-written reads | parent | OPEN | Target: single Workflow, parse depends on ingest task. Decide at plan. |
| D5-2 | scheduler | 1,8 | 02:00 analytics vs 02:10 finance overlap | parent | OPEN | Target: independent Workflows, no shared writes; finance depends on parse only. |
| D5-3 | scheduler | 9 | Sunday 06:00 `run_all` re-runs 6→7→8 over live 15-min jobs | parent | OPEN | Target: same DAG, `max_concurrent_runs=1`; `run_all` retired as separate code. |
| D5-4 | scheduler | 2,3 | Weekly Sunday 03:00/04:00 jobs | parent | OPEN | Target: Workflows, paused until STOP E. |
| D5-5 | scheduler | 4,5 | Daily 02:30/05:00 jobs | parent | OPEN | Same. |
| D7-1 | external | 6 | Mainframe CUSTBILL SFTP drop → S3 Transfer Family / landing volume; owner unnamed | customer | OPEN | Asked at STOP A (no owner named in approval). Re-ask at STOP B/C. Contract must fix encoding, malformed-record, empty-input, batch granularity. |
| D4-1 | consumer | 8 | `finance-reports@otterworks.dev` `.xls` distribution; `jake@` stale; sendmail dead since 2020 | customer | OPEN | Asked at STOP A (unanswered). Delivery mechanism decided at plan. |
| D4-2 | consumer | 5 | admin-service reads `reports/user-activity/<ds>/activity_report.json` — **INFERRED**: intake claim, no reader found in `services/` by repo grep | customer | OPEN | Confirm existence of the consumer at STOP B/C; default keep path + shape byte-compatible. |
| D3-1 | upstream | 3 | document-/file-service REST → MeiliSearch reindex | parent | OPEN | Scope decision at STOP B/C: keep as a Job (default). |
| D8-1 | governance | 1-5 | `config.ini` plaintext creds | parent | OPEN | Secret scope `ow_tp`, names only. Closed when wave 0 seeds the scope. |
| D8-2 | governance | all | Shared PAT, no service principal; attribution by `ns`/branch/PR | customer | DEFERRED(demo workspace) | Access model in `07_access_checklist.md`. |
| D9-1 | tolerance | all | Tolerance record v1 | user | CLOSED | Approved at STOP A, https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709 |
| D9-2 | decision | all | PR shape: 1 PR/unit vs README 3-PR stack | user | CLOSED | Approved at STOP A (D-002). |
| D10-4 | env | all | `AWS_DEFAULT_REGION` unset on the VM; 12/26 AWS probes `NoRegion` | parent | OPEN | Export `AWS_DEFAULT_REGION=us-east-1` in run env and child prompts; propose blueprint change. |
| D10-5 | access | all | Security reviewer for the access model and cutover-principal holder unnamed | customer | OPEN | Asked at STOP A (unanswered). Needed before STOP E, not before wave 0. |
| D3-2 | upstream | 1 | SQS `otterworks-analytics` (hardcoded URL, `analytics_daily.py:50-58`) + DynamoDB `otterworks-analytics-events` (py:111-140) feed J1; J1 deletes consumed SQS messages | parent | UNDECIDED | Options: bronze ingestion of both sources with fixture replay; SQS consumption semantics (delete) must be specified in the unit contract. |
| D6-1 | shared table | 2 | J2 archives then **deletes** from DynamoDB `otterworks-audit-events`, which the audit-service also writes (`services/audit-service/src/Config/AwsSettings.cs:8`, `infrastructure/terraform/modules/database/main.tf:131`) | customer | UNDECIDED | Options: legacy remains writer + lakehouse archive-only (no delete) during coexistence; delete re-enabled only at cutover. |
| D6-2 | shared table | 4 | J4 reads DynamoDB `otterworks-file-metadata` and **deletes** from S3 `files/*` owned by file-service (`services/file-service/src/config.rs:64`) | customer | UNDECIDED | Options: dry-run/report-only during coexistence; destructive quarantine only after cutover. |
| D4-3 | consumer | 3 | search-service reads MeiliSearch `documents`/`files` rebuilt by J3 (`services/search-service/app/config.py:8-17`) | customer | UNDECIDED | Options: keep J3 as a Databricks Job writing to MeiliSearch; or declare P-E out of lakehouse scope. Decide at STOP B/C. |
| D1-1 | intra lineage | 6→7 | Silver reads `ow_tp.bronze.custbill_raw` (`ns`,`source_file`,`line_no`,`raw_line`) instead of `incoming/*.dat`; one file = one batch (`CUSTBILL_analysis.md` §4.4) | parent | UNDECIDED | Interface fixed by wave-0 DDL; else U7 waits on U6 merge. Decide at STOP C. |
| D1-2 | intra lineage | 7→8 | Gold reads `ow_tp.silver.custbill_records` (§4.1) instead of `parsed/*.psv`; all-time aggregate per `ns` (`finance_excel_report.pl:43-58`) | parent | UNDECIDED | Same shape as D1-1. |
| D2-1 | shared object | 6,7,8,9 (+P-A..E) | Catalog/schemas/volume/scope, `dbx.py`, validators, dialect notes, **all table DDL** — inherited by every pipeline | parent | OPEN | Alias of D10-1/D10-2 for the wave-0 work list; children never run DDL on shared tables. |
| D2-2 | shared object | 9 | `etl/legacy-extra/crontab` holds P-B's four lines next to the P-A..E lines in `etl/crontab`; U9 replaces only P-B's lines; legacy files untouched until STOP E | parent | UNDECIDED | Cutover-time only. |
| D3-3 | upstream feed | 6,7 | CUSTBILL file contract: 65-byte records, HDR/TRL lines, trailer count bytes 4-13 (`parse_custbill_fixedwidth.sh:79-84,120,144`); encoding (ASCII/EBCDIC), terminator (`\n`/`\r\n`), HDR/TRL mid-file NOT fixed by export | customer (mainframe team) | UNDECIDED | Default from fixtures: ASCII, `\n`, HDR first/TRL last, empty body = valid 0-row file. Ask with D7-1 at STOP C. |
| D4-4 | consumer | 8 | Finance also collects `reports/*.xls` "from the shared drive" (`finance_excel_report.pl:79-81`) — **INFERRED**: no share/mount in export | customer | UNDECIDED | Ask at STOP C; if real, export copy or repoint at STOP E. |
| D8-3 | governance | 6 | Fixture SFTP credential (`docker-compose.sftp.yml`, user `mainframe`) → secret scope `ow_tp`, key `sftp_password`, name only; production SFTP/Transfer Family credential customer-issued | parent / customer | UNDECIDED | None for fixtures. |
| D10-6 | env | 6 | Serverless tasks have no route to a laptop-bound SFTP fixture; live ingest needs S3/Transfer Family landing or parent-side push into `/Volumes/ow_tp/bronze/landing` | parent | UNDECIDED | Shapes U6 live recon path; fixture path unaffected. Decide at STOP C. |
| D6-x | shared table | – | P-B has **no** shared table with a non-migrated writer (file-based) | – | N/A | Recorded so the sweep is provably complete. |
| D8-4 | governance | 7,8 | `cust_name`/`cust_id` carry customer identity; legacy has no classification — PII regime (masking/row filters on `ow_tp.silver.custbill_records`) is a customer policy decision | customer | OPEN | Raised in `CUSTBILL_plan.md` §6 as GAP; needed before STOP E, not before wave 0. |
