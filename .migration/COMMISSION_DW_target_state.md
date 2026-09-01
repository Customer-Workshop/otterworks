# Target state — Commission Pay `COMMISSION_DW` → Databricks lakehouse

Version 1 (2026-09-01, pre-STOP A). Every field is **FACT** (cited) or **PROPOSED** (default, confirmed once at STOP A). Sources: `.migration/00_intake_template.md` (intake), `docs/tech-partnerships/contracts/README.md` (shared rules of the existing Databricks track, the reference implementation for CORE), `docs/tech-partnerships/contracts/schema/*.schema.json` (machine-readable evidence contract), plugin skills `unity-catalog-conventions`, `data-reconciliation`, `backfill-planner`, `databricks-auth-cli`, `dlt-pipelines`, knowledge note "OtterWorks TP demo credentials map & platform limits".

A child that has read only CORE + its surface profile + DATA/DEPENDENCY must be able to write conformant code. Nothing below may be guessed at by a child.

## CORE (everything)
| Field | Value | Status | Source |
|---|---|---|---|
| Workspace | secret `DATABRICKS_DEMO_HOST` / `DATABRICKS_DEMO_TOKEN` (shared demo workspace; PAT scopes sql, unity-catalog, jobs, secrets, workspace, files) | FACT | knowledge note; intake §2 |
| Compute | serverless SQL warehouse `565cd2fd713738c4` only; serverless notebook tasks allowed; **never create clusters or any resource with an hourly cost** | FACT | intake §2; contracts/README shared rules |
| Unity Catalog layout | catalog `ow_tp`; schemas `bronze`, `silver`, `gold`, `ops`; every object suffixed `_<ns>` (`ow_tp.silver.fact_commission_cdw`); managed volume `/Volumes/ow_tp/bronze/landing/<ns>/<unit>/…`; secret scope `ow_tp`; notebooks `/Shared/ow_tp/<ns>/…`; jobs `ow_tp_<ns>_<unit>` | FACT (layout) / PROPOSED (`ops` schema, job name pattern) | contracts/README; intake §2 |
| Namespace | `NS=cdw` for this run (rehearsal; torn down after). `demo` is reserved | PROPOSED | intake §2 |
| Shared-workspace rules | never read/write/delete an unprefixed object; never DDL on a table another namespace uses; a child never runs `CREATE/DROP/REPLACE` on a shared table — it owns only `*_cdw` objects listed in its batch packet | FACT | knowledge note; contracts/README |
| Naming | lowercase snake_case; **preserve legacy table and column names** (`dim_agent.agent_key`, `fact_commission.commission_amt`…); forced renames recorded in the unit mapping table | FACT | `unity-catalog-conventions` |
| Delta conventions | managed Delta tables; `loaded_at` and other server-side timestamps are excluded from recon; liquid clustering only where the dictionary names it (`fact_commission_cdw (period_key, agent_key)`) | PROPOSED | intake §6 |
| Code language | Spark SQL first (the estate is SQL + one PL/SQL package); PySpark only for orchestration glue and the recon harness; no Scala | PROPOSED | — |
| Repo topology | single repo `Cognition-Partner-Workshops/otterworks` plays SOURCE (legacy schema and loader definitions under `services/industry-solutions/insurance/db/` — `olap/01_star_schema.sql`, `olap/02_etl_pkg.sql`, `setup/01_users.sql`), TARGET (`scripts/tp_dbx/`, `infrastructure/terraform-databricks/jobs_<unit>.tf` if used, SQL under `dbx/commission_dw/`) and DOCS (`.migration/`, `docs/tech-partnerships/contracts/`) | FACT | intake §2 |
| Branch / PR | run branch `tp-run/databricks-20260901T205306Z`; unit branches `migrate/commission-dw/<wave>-<unit>`; **one PR per unit, never stacked**, target = run branch; PR reviewers: engagement lead; 2 review rounds; `tp-pre-pr-self-check` before opening; every PR passes `make tp-smoke` | FACT | intake §5; knowledge note (the older 3-PR-stack rule in contracts/README is superseded by the measured single-PR rule) |
| CI gates | `make tp-smoke` (golden path), `make tp-validate-schemas`, `make tp-validate-recon FILE=<unit>.recon.json` | FACT | Makefile |
| Evidence contract | every unit PR commits `<unit>.recon.json` (`"kind":"recon-report"`, schema `recon-report.schema.json`) plus a ≤30-line `recon.summary.md`; values recomputed from the target; idempotency proven by rerun; unverified paths listed | FACT | contracts/README; `data-reconciliation` |
| Secrets | referenced by name only; never in code, artifacts, PR bodies or logs | FACT | plugin rule |
| Forbidden patterns (drift rules → PR rejected) | DDL/DML on Oracle; unprefixed Databricks objects; cluster creation; `terraform apply/destroy` from a child; `GENERATED ALWAYS AS IDENTITY` on migrated key columns; `WHEN OTHERS THEN NULL`-style swallowing; recon compared against self-generated rows; a recon report without tolerance version + mode header; naming the requester or emails in PR content | FACT | intake §6; contracts/README; knowledge notes |

## SQL profile (tables, MV) — in scope
| Field | Value | Status |
|---|---|---|
| Dialect policy | Oracle → Databricks SQL by generic ANSI translation plus the physical/dialect dictionary from `02_analysis` (no `oracle-plsql` plugin skill exists; building a stub is W0-1) | FACT (intake §6) |
| Function equivalence | `NUMBER(p,s)`→`DECIMAL(p,s)`; `NUMBER` (no precision)→`DECIMAL(38,10)` unless the dictionary pins narrower; `DATE`→`DATE`; `VARCHAR2(n)`→`STRING` (`period_month` stays a `YYYY-MM` string, never a date); `TRUNC(d,'MM')`→`date_trunc('MONTH', d)::date`; `NVL`→`coalesce`; `DECODE`→`CASE`; `ROUND` half-away-from-zero: Spark `round()` on DECIMAL is HALF_UP — identical for positives, negatives must be covered by a named test; `SYSTIMESTAMP`→`current_timestamp()` (excluded from recon); `\|\|`→`concat` | PROPOSED |
| Materialization | `DIM_*`, `FACT_COMMISSION` → silver Delta tables; `MV_AGENT_COMMISSION_SUMMARY` → gold Delta table rebuilt by the converted job (COMPLETE/DEMAND refresh semantics = full rebuild; DLT MV is an accepted alternative if the pilot proves it) | PROPOSED |
| Performance | no partitioning (tiny estate); liquid clustering on `fact_commission_cdw (period_key, agent_key)`; constraint indexes dropped; `UX_FACT_ROW` becomes the MERGE key and recon key | PROPOSED |
| Report-output contract | MV compared as a full result set ordered by (`agent_code`, `full_name`, `period_month`, `line_of_business`) | PROPOSED |

## PIPELINE profile (`DW_ETL_PKG.LOAD_COMMISSION_FACTS`) — in scope
| Field | Value | Status |
|---|---|---|
| Target runtime | Databricks Job (serverless) running Spark SQL `MERGE` statements, parameterised by `ns` and `period`; DLT deferred unless pilot recommends | PROPOSED |
| Layering | bronze = landed snapshots of the four `COMMISSION_PAY` inputs (D3 feed) and of the DW tables (recon baseline); silver = `dim_*`, `fact_commission` **initialised from the `COMMISSION_DW` baseline snapshots (explicit `agent_key`/`product_key`/`period_key`/`fact_id` values carried over, DEC-003)** and thereafter maintained by the converted loader MERGE from the bronze feed; `dim_agent`, `dim_product`, and `dim_period` each carry `loaded_at TIMESTAMP NOT NULL DEFAULT current_timestamp()`-equivalent (set in INSERT, excluded from recon); new rows receive keys allocated as `max(key) + row_number() OVER (ORDER BY natural key)` inside the single-writer job (deterministic, collision-free because the job is the only writer); gold = `mv_agent_commission_summary` | PROPOSED |
| Load pattern | MERGE (upsert) keyed on natural keys, mirroring the PL/SQL; **idempotent**: rerun for the same period yields an identical row set (excluding `loaded_at`) | FACT (intake §4) |
| Error / reject rows | no silent swallowing; rows failing NOT NULL / FK lookups go to `ow_tp.ops.quarantine_cdw` with reason; the legacy package's exception handling is documented in the dictionary and its `WHEN OTHERS` (if any) is **not** reproduced | PROPOSED |
| Restart | full rerun is safe (MERGE); no checkpoint needed at this size | PROPOSED |
| Parameterisation / logging | `ns`, `period_month`; run log row in `ow_tp.ops.run_log_cdw` (unit, run id, rows in/out, started/finished) | PROPOSED |

## ORCHESTRATION profile
| Field | Value | Status |
|---|---|---|
| Legacy schedule | none visible (no `DBMS_SCHEDULER` job; ETL invoked on demand, per period) | FACT (intake §1) |
| Target | one Databricks Job `ow_tp_cdw_load_commission_facts` with tasks **ingest feed** (validate `manifest.json` under `/Volumes/ow_tp/bronze/landing/cdw/feed/`, sha256 + rowcount check, then `CREATE OR REPLACE TABLE ow_tp.bronze.<feed>_cdw AS SELECT … FROM read_files(...)` for all four inputs — atomic per table, fail-fast before any silver task) → load dims → load fact → refresh gold → recon; **schedule PAUSED** (nothing runs on a schedule in this workspace); trigger by hand | PROPOSED |
| Completion signalling | job run state + `ops.run_log_cdw` row | PROPOSED |
| Alerting | recon failure = job task failure; parallel-run remediation is event-driven per `!dbx_parallel_run` | PROPOSED |

## CONSUMER profile
| Field | Value | Status |
|---|---|---|
| Known consumers | none detectable (no grants, no query history — D4 evidence gap); code search is the inventory's sweep | FACT (intake §1, D4-1) |
| Policy | if the sweep finds none: cutover = publish gold + document; re-point vs rebuild decided per consumer if any surfaces later | PROPOSED |

## ML-SCORING profile
N/A — no model training or scoring reads `COMMISSION_DW` (intake §1: 0 views, no consumers, no ML objects).

## DATA / DEPENDENCY profile
| Field | Value | Status |
|---|---|---|
| Coexistence | **snapshots** (Lakehouse Federation is topologically unreachable: source is loopback-only) — D10-1 | FACT (intake §3) |
| Snapshot standard | one UTF-8 CSV per object, `ORDER BY` primary key (MV by grouping columns), `loaded_at` empty, `manifest.json` (object, row count, sha256, extraction time, source, `FIXTURE_SOURCE` path); local transport check via `FIXTURE_SOURCE=… make tp-fixture-land NS=cdw` + `tp-fixture-verify` (W0-2), then parent-owned Files API upload to `/Volumes/ow_tp/bronze/landing/cdw/<unit>/` with sha256 re-read (see `01_conventions.md`) | FACT (intake W0-2) / PROPOSED (upload step) |
| Dual-write | none (legacy read-only; no writers to migrate) | FACT |
| Recon mode | **DEGRADED** — every report header names it; gate language never borrows LIVE confidence; an in-perimeter recon run by the customer is an entry criterion for STOP E | FACT (intake §4) |
| PII / masking | agent names (`DIM_AGENT.full_name`) are the only person data; no legacy masking policy exists → no D8 masks migrated; note in decisions | PROPOSED |
| Decommission criteria | parallel-run window green for the agreed period + STOP E authorization by the customer-held principal | PROPOSED |

## Cross-profile reconciliation
- Error handling: PIPELINE quarantines, SQL profile has nothing to quarantine (pure tables) — deliberate, not drift.
- Naming: both profiles preserve legacy names; the `_cdw` suffix is CORE.
- Idempotency: defined once in CORE evidence contract; PIPELINE inherits it.

## Open questions queued for STOP A
1. Security reviewer contact (OPEN in intake) — proposed: mark N/A for this engagement.
2. Cutover principal holder (OPEN) — proposed: "customer-held, named at STOP E"; children never hold it.
3. Confirm all PROPOSED rows above and in `03_recon_tolerances.md`.
