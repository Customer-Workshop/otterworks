# D4 OW_BILLING application/consumer census

## Scope and method

- Repository: `/home/ubuntu/repos/otterworks`.
- Branch observed: `tp-run/databricks-20260914T183234Z`; it was not changed.
- Search was case-insensitive and excluded `services/legacy-billing/db/oracle/**`,
  `.migration/**`, and `docs/migration/**`, plus vendored/generated dependency
  directories when classifying source consumers.
- Direct consumer means code/config that connects to Oracle or issues Oracle SQL.
  The report separately lists file-based CUSTBILL and documentation references so
  they are not mistaken for Oracle table readers.
- No repository source files were modified. This report and the search evidence
  were written only under `/home/ubuntu/probe/`.

## Consumer census

| Path | Kind | OW_BILLING tables/packages touched | Read or write | Connection mechanism | Evidence line cite |
|---|---|---|---|---|---|
| `services/legacy-billing/app/reports.py` | report | Reads `INVOICE_HEADER`, `INVOICE_LINE`, `CODES`, `CUSTOMER_MASTER` | Read only | Python `oracledb.connect`; `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`; defaults are the local billing fixture | `reports.py:26-30,32-79,122-137,149-181` |
| `services/legacy-billing/app/app.py` | app service | Hosts the Oracle-backed report blueprint; its other routes use Postgres `billing.*` functions, not OW_BILLING | Oracle path read only; other app routes read/write Postgres | Flask `app.register_blueprint(reports)`; `reports.py` owns the Oracle connection; `app.py` separately uses `psycopg` | `app.py:9-22,51-59`; `reports.py:122-137` |
| `services/legacy-billing/app/requirements.txt` | doc | Dependency for the report consumer: `oracledb` | N/A | Python package declaration | `requirements.txt:1-4` |
| `docker-compose.procs.yml` | doc | Indirectly exposes the report's Oracle path; report tables are those in `reports.py` | Read only through report service | `legacy-billing` container passes `ORACLE_HOST` and `ORACLE_PORT`; the report supplies remaining defaults; `billing-service` in this file is Postgres-only | `docker-compose.procs.yml:26-52` |
| `docker-compose.oracle-billing.yml` | doc | OW_BILLING fixture; healthcheck queries `FIXTURE_META` | Fixture startup/healthcheck only; no application table DML here | Oracle Free container, `ORACLE_BILLING_PWD` environment key, host port mapping to listener port 1521, service `FREEPDB1`, `sqlplus` healthcheck | `docker-compose.oracle-billing.yml:1-27` (password value intentionally not reproduced) |
| `testdata/legacy/oracle_billing_seed.py` | batch job | `CUSTOMER_MASTER`, `ENTITY_ATTR_VALUE`, `CUSTOMER_MASTER_HIST`, `INVOICE_HEADER`, `INVOICE_LINE`, `TENANTS`, `SUBSCRIPTIONS`, `USAGE_EVENTS`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS`, `INVOICE_LINES`, `INVOICES`, `RATING_RESULTS`, `RATING_PERIODS`, `CREDIT_NOTES`, `SUBSCRIPTIONS_HIST` | Read/write; namespace cleanup deletes and seed inserts | Python `oracledb.connect`; `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SERVICE`; invoked by `make oracle-billing-seed` | `oracle_billing_seed.py:2-8,80-112,120-149,162-366` |
| `procs/harness/oracle_record.py` | test | Reset tables listed below; invokes all mapped PL/SQL packages through `oracle_map.yaml`: `PKG_PLANS`, `PKG_RATING`, `PKG_INVOICING`, `PKG_DUNNING`; uses `PKG_OW_UTIL` through mapped SQL | Read/write: reset deletes and static-seed inserts; package calls/probes read and may mutate fixture state; writes local transcripts | Python `oracledb.connect`; `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SERVICE`; `callfunc`/`callproc` and SQL probes | `oracle_record.py:1-12,26-45,77-85,164-178,209-249,296-320,341-359` |
| `procs/oracle/oracle_map.yaml` | test | Package calls for `PKG_PLANS`, `PKG_RATING`, `PKG_INVOICING`, `PKG_DUNNING`, `PKG_OW_UTIL`; SQL probes read `SUBSCRIPTIONS`, `RATING_RESULTS`, `RATING_PERIODS`, `CREDIT_NOTES`, `INVOICES`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS` | Declarative read probes plus package calls; no connection by itself | YAML contract consumed by `oracle_record.py` | `oracle_map.yaml:1-23,26-176` |
| `procs/harness/oracle_parity.py` | test | Oracle transcript side of the package/table contract; does not query Oracle directly | Reads previously recorded Oracle and Postgres transcripts; writes local parity reports | Filesystem JSON/MD comparison, not an Oracle DSN | `oracle_parity.py:1-11,20-23,28-33,67-101,104-158` |
| `procs/oracle/transcripts/**/*.json` and `procs/oracle/transcripts/index.json` | test | Recorded package entrypoints and OW_BILLING scenario results | Read as immutable test evidence | Filesystem artifacts consumed by `oracle_parity.py` | `procs/README.md:153-162`; `oracle_parity.py:28-33` |
| `scripts/tp_pain/mongodb.py` | report | Reads `CUSTOMER_MASTER`, `CUSTOMER_MASTER_HIST`, and `ENTITY_ATTR_VALUE`; also inventories report, seeder, and parity touch points | Read only; module explicitly issues `SELECT`s | Python `oracledb.connect`; CLI/env defaults `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SERVICE` | `mongodb.py:1-15,27,64-67,78-84,95-108,116-171` |
| `scripts/tp-pain-mongodb.sh` | batch job | Wrapper for the read-only Oracle inspection above | Read only through child script | `uv run --with oracledb==2.5.1` invokes `scripts/tp_pain/mongodb.py` | `tp-pain-mongodb.sh:1-5` |
| `Makefile` Oracle targets | doc | Orchestrates the fixture, seeder, recorder, and parity consumer set | `oracle-billing-seed`, `oracle-record`, and `oracle-parity` write fixture/transcript state; smoke target itself is intended as validation | Compose; `uv` with `oracledb`/`pyyaml`; environment variables passed to child commands | `Makefile:102-133,264-286` |
| `.github/workflows/tp-golden-smoke.yml` | test | Checks Oracle billing target/config entry points; no table query | Validation only; does not boot Oracle | `make -n` dry-runs and `docker compose ... config`; workflow comments/state show no Oracle boot | `tp-golden-smoke.yml:21-45` |
| `services/legacy-billing/tests/test_reports.py` | test | Exercises the report contract backed by `INVOICE_HEADER`, `INVOICE_LINE`, `CODES`, and `CUSTOMER_MASTER` indirectly through SQL fixture keys | Read contract behavior mocked; no live Oracle connection | Pytest monkeypatches `reports_module.oracle_query`; tests 503 behavior when the estate is unavailable | `test_reports.py:29-39,72-105` |
| `frontend/admin-dashboard/src/app/core/services/billing-report.service.ts` | app service | Consumes the two report endpoints whose documented legacy source is OW_BILLING | Read through HTTP; no direct Oracle access | Angular `HttpClient` via `/billing-api/api/reports` | `billing-report.service.ts:6-20`; contract `billing-report-contract.md:3-19` |
| `frontend/admin-dashboard/src/app/pages/billing-report/billing-report.component.ts` | app service | Displays report/reconciliation data from the Oracle-backed report contract | Read through HTTP; no direct Oracle access | Injects `BillingReportService` and calls both endpoints | `billing-report.component.ts:178-209`; contract `billing-report-contract.md:3-19` |
| `frontend/admin-dashboard/src/app/pages/billing-report/billing-report.component.spec.ts` | test | Fixture identifies `OW_BILLING`, `INVOICE_HEADER`, `INVOICE_LINE`, and `CODES` | Mocked HTTP read; no live Oracle connection | Angular `HttpTestingController` returns legacy Oracle-shaped report data | `billing-report.component.spec.ts:7-36,55-74,82-109` |
| `docs/tech-partnerships/billing-report-contract.md` | doc | Documents `INVOICE_HEADER`, `INVOICE_LINE`, `CODES`, `CUSTOMER_MASTER` and the Oracle env contract | N/A | Documents `ORACLE_HOST`/`PORT`/`USER`/`PASSWORD`/`SERVICE` and the report backend boundary | `billing-report-contract.md:3-29,52-81,83-92` |
| `docs/tech-partnerships/README.md` | doc | Manifest examples include `CUSTOMER_MASTER` and `INVOICE_LINE`; fixture is `OW_BILLING` | N/A | Documents Compose/Make wiring and the `FREEPDB1`/port convention | `README.md:14-29,31-59,67-81` |
| `procs/README.md` | doc | Documents all 12 package entrypoints and Oracle transcript/probe flow | N/A | Documents `python-oracledb`, recorder, parity comparator, and immutable transcripts | `procs/README.md:114-166` |
| `docs/tech-partnerships/runbook-mongodb.md` | doc | Documents `CUSTOMER_MASTER`, `CUSTOMER_MASTER_HIST`, `ENTITY_ATTR_VALUE`, `INVOICE_HEADER`, `INVOICE_LINE` and migration consumers | N/A | Includes the operator `sqlplus` examples and the Mongo migration child-session contract; examples are documentation, not executed by the census | `runbook-mongodb.md:19-31,50-74,156-160,183-215` |
| `docs/tech-partnerships/runbook-aws.md` | doc | Documents `CUSTOMER_MASTER`, EAV/invoices, `PKG_RATING`, `PKG_INVOICING`, `PKG_DUNNING`, and scheduler jobs | N/A | Documents `sqlplus` access and proposed Oracle-exit work units | `runbook-aws.md:16-20,137-160,218-223` |
| `.agents/skills/oracle-billing-estate/SKILL.md` | doc | Documents `CUSTOMER_MASTER`, `INVOICE_HEADER`, `INVOICE_LINE`, `ENTITY_ATTR_VALUE`, `TENANTS` | N/A | Documents container `sqlplus`, listener port 1521, service name, and fixture Make targets | `SKILL.md:6-30` |

### Adjacent CUSTBILL and analytics consumers (no direct Oracle access found)

These paths were requested because they are part of the legacy billing/batch
surface. Their inspected code reads and writes flat files, not OW_BILLING tables.
They should not be counted as direct Oracle readers.

| Path | Kind | Tables/packages touched | Read or write | Connection mechanism | Evidence line cite |
|---|---|---|---|---|---|
| `etl/legacy-extra/crontab` | batch job | None; `analytics_daily.py` is a separate cron entry and no Oracle command is present | Reads/writes ETL files through scheduled jobs | Host cron; SFTP/file paths; finance report at 02:10 overlaps analytics at 02:00 | `crontab:1-33` |
| `etl/legacy-extra/jobs/sftp_ingest_poll.ksh` | batch job | None | Reads SFTP drop; writes `incoming/` and timestamped `archive/` files | KornShell filesystem/SFTP-drop polling; no Oracle driver or SQL client | `sftp_ingest_poll.ksh:1-69` |
| `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh` | batch job | None | Reads fixed-width `.dat`; writes `.psv` and renames inputs `.done` | Bash plus `sed`/`awk`/`cut`; no Oracle driver or SQL client | `parse_custbill_fixedwidth.sh:1-80` |
| `etl/legacy-extra/jobs/finance_excel_report.pl` | report | None | Reads parsed `.psv`; writes CSV renamed `.xls` and attempts sendmail delivery | Perl filesystem/readdir and sendmail pipe; no Oracle driver or SQL client | `finance_excel_report.pl:1-90` |
| `etl/legacy-extra/run_all.sh` | batch job | None | Orchestrates file-based ingest, parse, and finance report | Bash child-process calls and sleeps; no Oracle connection | `run_all.sh:1-27` |
| `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md` | doc | None; explicitly inventories the four file-based jobs | N/A | Documents host-run `legacy-etl-*` targets and states the chain is not wired into default CI | `ETL_UPGRADE_GUIDE_ADDENDUM.md:3-22,29-41,64-68` |
| `scripts/tp_dbx/legacy_pain.sh` | batch job | None | Reads/writes the isolated CUSTBILL sandbox and reports file-chain blast radius | Invokes the ksh/bash/Perl chain; no Oracle connection | `legacy_pain.sh:1-26,54-80,87-135` |
| `scripts/tp_dbx/sql.py` and `scripts/tp_dbx/showcase.py` | batch job | None; Databricks CUSTBILL bronze/silver/gold objects only | Reads/lands CUSTBILL files and writes Databricks pipeline/recon artifacts | Databricks SQL/SDK and local landing files; no Oracle driver or DSN | `sql.py:1-44,59-93,272-309`; `showcase.py:9-18,124-178,237-271` |
| `docs/tech-partnerships/runbook-databricks.md` and `docs/tech-partnerships/runbook-modernize-otterworks.md` | doc | None; describe CUSTBILL file migration | N/A | Documents the file chain and Databricks replacement; no Oracle connection | `runbook-databricks.md:46-53,100-127`; `runbook-modernize-otterworks.md:44-76` |

The CUSTBILL addendum also says the finance report overlaps
`analytics_daily` (`ETL_UPGRADE_GUIDE_ADDENDUM.md:47-58`), but no
`analytics_daily.py` implementation or Oracle connection was found in the
searched repository paths.

## Tests and smoke-gate coverage

Tests or test artifacts that reference the OW_BILLING estate:

1. `services/legacy-billing/tests/test_reports.py` — backend report contract,
   mocked Oracle query results, Oracle source metadata, and 503/unavailable
   behavior (`test_reports.py:29-39,72-105`).
2. `frontend/admin-dashboard/src/app/pages/billing-report/billing-report.component.spec.ts`
   — mocked report payload identifies the Oracle estate and checks the source
   badge, baseline banner, totals, and unavailable state
   (`billing-report.component.spec.ts:7-10,55-109`).
3. `procs/scenarios/**/*.yaml`, `procs/oracle/oracle_map.yaml`, and
   `procs/oracle/transcripts/**/*.json` — declarative parity scenarios,
   Oracle package mappings, and immutable Oracle recordings. These are exercised
   by `make oracle-record` / `make oracle-parity`, not by the default
   `tp-smoke` test commands (`procs/README.md:132-162`).
4. The `tp-golden-smoke` estate-targets job does **not** boot Oracle or run the
   backend/UI test suites. It dry-runs the Oracle/legacy Make targets, lints the
   Oracle Compose config, checks `make -n test`, and runs offline portal
   self-tests (`.github/workflows/tp-golden-smoke.yml:21-45`).
5. No dedicated CUSTBILL unit-test file was found. The addendum explicitly says
   the host-run CUSTBILL chain is not wired into `make test` or CI
   (`ETL_UPGRADE_GUIDE_ADDENDUM.md:64-68`).

`services/billing-service/**` was not counted as an Oracle consumer: its
connection is a separate Postgres URL and its similarly named billing plans
are target-side procedures, not evidence of an OW_BILLING connection
(`docker-compose.procs.yml:53-85`; `services/legacy-billing/app/app.py:15-22`).
Likewise, Oracle references under `services/industry-solutions/insurance/**`
belong to the separate Commission Pay estate, not `OW_BILLING`.

## Five-line smoke/self-check summary

1. `make tp-smoke` dry-runs `oracle-billing-up`, `seed-legacy NS=ci`, `legacy-etl-list`, and `procs-parity NS=ci`, then validates Oracle Compose syntax.
2. It also checks `make -n test`, renders offline TP portal artifacts, runs portal self-tests, and performs API Gateway vet/test/build plus Collab lint/test/build and Search pytest.
3. `tp-pre-pr-self-check` requires namespace-scoped `ow_tp`/`ow-tp-` objects, no shared-table destructive DDL, fail-closed NULL/missing attribution, and no secrets or real distribution-list addresses.
4. It requires rerun-safe cleanup, retained evidence/recon artifacts, contract-aligned parity/tolerance, an actual idempotency rerun, and target-side recomputation of recon values.
5. It requires explicit unverified-path coverage, the `kind: recon-report`/`*.recon.json` format where applicable, capability preflight, and green `make tp-smoke` (`SKILL.md:8-34`; `Makefile:264-286`).

## Graphviz

Command checked: `command -v dot` (and `dot -V` only if found).

Result: **`dot` is not installed or not on `PATH`**; the lookup returned no
path, so no Graphviz version was available.

## Search exclusions and conclusion

The excluded Oracle schema source tree was not enumerated as a consumer, per
request. The census found one live application report path, one deterministic
Oracle seeder, one direct read-only inspection/report path, one direct Oracle
parity recorder with fixture writes, the declarative parity map/artifacts,
fixture/Compose and Make wiring, the backend/UI contract tests, and the
documented/file-based CUSTBILL batch surface. Generic uses of words such as
`tenants`, `plans`, `notifications`, and `codes` without Oracle context were
excluded.
