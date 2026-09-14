# OtterWorks billing -> Databricks: engagement context

Front door: `!dbx_migrate_oltp` (operational database estate, Lakebase). Pipeline 1 = monthly
invoicing (Oracle `OW_BILLING`). Pipelines 2 and 3 will share this ledger later.

Row marking: **FACT** (intake, confirmed by the customer 2026-09-14), **DISCOVERED** (probed by this
session, evidence in `07_access_checklist.md`), **PROPOSED** (default, confirmed at STOP A).

## Engagement

| Field | Value | Mark |
|---|---|---|
| Engagement | OtterWorks billing estate -> Databricks (Lakebase operational track + Delta analytical track) | FACT |
| Pipeline 1 | Monthly invoicing: `OW_BILLING` packages `pkg_plans`, `pkg_rating`, `pkg_invoicing`, `pkg_dunning`, `pkg_ow_util` and the tables they touch | FACT |
| stop_mode | `soft` (60 s window, then the recommended default is accepted and recorded) | FACT |
| Stops that always block regardless of mode | STOP E; any stop whose default would change tolerances, widen scope, or touch the legacy source | FACT |
| Orchestrator session | this session (`devin-8c378c45e9024737a3d45c0d6f87ad71`), child of parent `devin-7e19cb53998e471c9dc41f46d6a0058f` | FACT |
| Interaction contract | Stops are posted in this session as one message (decision, recommendation, exact approving reply); the parent session relays to Slack `#ow-tp-alerts` and replies with the customer's exact words. One question at a time, concrete options. Events: STOP A/B/C/E, wave close (STOP D), fan-out halt. Nothing else pings. | FACT |
| Notification contract | none from this session directly (parent owns `#ow-tp-alerts`); no daily digest, event-only | FACT / PROPOSED (digest) |
| PR reviewer | customer lead (cutover principal holder), 2 review rounds per PR | PROPOSED |

## Source estate

| Field | Value | Mark |
|---|---|---|
| Engine / version | Oracle Database Free 23ai (`container-registry.oracle.com/database/free:latest`), PDB `FREEPDB1` | FACT |
| Schema | `OW_BILLING` | FACT |
| Host | EC2 `i-0be201ad6412c5e5e`, EIP `52.201.36.9:1521`, SG `sg-0eaf11f4434260e1`, AWS account 599083837640 us-east-1 | FACT |
| Redo posture | `LOG_MODE=ARCHIVELOG`, `SUPPLEMENTAL_LOG_DATA_MIN=NO` (customer DBA-owned D10-1) | FACT |
| Objects | 19 tables (+`FIXTURE_META` marker), 5 packages / 19 routines, 7 triggers, 5 sequences, 2 `DBMS_SCHEDULER` jobs (disabled: `JOB_NIGHTLY_DUNNING` 02:00, `JOB_PURGE_AUDIT_LOG` 03:30) | FACT / DISCOVERED |
| Seed | `NS=demo SCALE=demo`, seed SCN `2137574`: `CUSTOMER_MASTER` 25 000, `INVOICE_HEADER` 18 750, `INVOICE_LINE` 150 000 (37 planted orphans), `ENTITY_ATTR_VALUE` 8 333, 60 demo tenants (`name LIKE 'demo::%'`) | FACT |
| Companion batch surfaces (not pipeline 1) | CUSTBILL: 4 jobs (ksh SFTP poller, bash/awk fixed-width parser, Perl report, run_all); analytics: 5 Python cron jobs + Scala `UsageRollupJob` | DISCOVERED (intake) |
| Read-only credential | `ORACLE_OW_BILLING_RO_DSN` = AWS Secrets Manager `ow-tp/oracle/ow_billing_ro` (us-east-1), read with `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`. Principal `ow_billing_ro`: CREATE SESSION + SELECT ANY TABLE + SELECT ANY DICTIONARY; INSERT rejected (ORA-41900) | FACT |
| Source is read-only | No DDL, DML, grants, CDC or supplemental-logging changes from any migration session, ever | FACT |
| Estate docs | `services/legacy-billing/db/oracle/README.md`, `.../schema`, `.../packages`, `.../setup`, `.agents/skills/oracle-billing-estate/SKILL.md` | FACT |

## Target

| Field | Value | Mark |
|---|---|---|
| Workspace | `DATABRICKS_DEMO_HOST` (shared demo workspace) | FACT |
| Auth | `DATABRICKS_DEMO_TOKEN` (PAT, files scope). `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` unset when using the CLI. The identity is a human user, not a migration service principal (see D10-4 in `04_dependency_register.md`). | FACT / DISCOVERED |
| Migration catalog | `ow_tp`; schemas `bronze`, `silver`, `gold`, `ops`; volume `/Volumes/ow_tp/bronze/landing`; secret scope `ow_tp`; workspace dir `/Shared/ow_tp`. All parent-created. | FACT |
| Compute | existing serverless SQL warehouse + serverless notebook tasks only; no clusters, no hourly-cost resources | FACT |
| Shared rules | everything prefixed `ow_tp`, jobs named `ow_tp_<unit>`, `ns=demo` parameter, volume paths `<ns>/<unit>/...` (`docs/tech-partnerships/contracts/README.md`) | FACT |
| Lakebase project | id `ow-tp-billing` (display `ow_tp-billing`), branch `production`, endpoint `primary`, host `ep-damp-river-d1lws1dv.database.us-west-2.cloud.databricks.com`, db `databricks_postgres`. Lakebase Postgres Autoscaling tier. | FACT |
| Lakebase credential | 1-hour credential from `databricks postgres generate-database-credential projects/ow-tp-billing/branches/<branch>/endpoints/primary` (PAT auth); no static DSN secret; children derive at runtime. Logical name `LAKEBASE_OW_TP_BILLING_DSN`. | FACT |
| Lakebase write policy | one branch per wave batch (copy-on-write, TTL, dropped at wave close); **no child writes `production`**; branch names `mig-<pipeline>-w<N>-<batch>` | FACT / PROPOSED (naming) |
| Repo roles | SOURCE + TARGET + DOCS = `Cognition-Partner-Workshops/otterworks`, branch `tp-run/databricks-20260914T183234Z`; `.migration/` at repo root; unit PRs one per unit into that branch; never `tech-partnerships` or `main` | FACT |
| Target-state profiles | `docs/migration/ow_billing_target_state.md` (CORE, SQL, PIPELINE, ORCHESTRATION, CONSUMER, LAKEBASE, DATA/DEPENDENCY; ML-SCORING N/A) | this session |

## Track split (every in-scope table; provenance = static grep of `services/legacy-billing/db/oracle/{packages,schema}` write statements, cross-checked against live `ALL_SOURCE`)

| Table | Track | Provenance | Mark |
|---|---|---|---|
| `TENANTS` | operational | `pkg_dunning` UPDATE (suspend) | FACT (write set) |
| `SUBSCRIPTIONS` | operational | `pkg_plans` INSERT/UPDATE, `pkg_dunning` UPDATE; triggers `trg_subscriptions_hist`, `trg_sub_no_uncancel` | FACT |
| `RATING_PERIODS` | operational | `pkg_rating` INSERT/UPDATE | FACT |
| `RATING_RESULTS` | operational | `pkg_rating` INSERT/UPDATE | FACT |
| `INVOICES` | operational | `pkg_invoicing` INSERT/UPDATE x2 | FACT |
| `INVOICE_LINES` | operational | `pkg_invoicing` INSERT/DELETE | FACT |
| `CREDIT_NOTES` | operational | `pkg_invoicing` UPDATE | FACT |
| `DUNNING_ATTEMPTS` | operational | `pkg_dunning` INSERT | FACT |
| `NOTIFICATIONS` | operational | `pkg_dunning` INSERT | FACT |
| `BILLING_AUDIT_LOG` | operational | `pkg_ow_util.log_msg` INSERT (autonomous txn), `JOB_PURGE_AUDIT_LOG` DELETE, trigger `trg_billing_audit_log_id` | FACT |
| `CODES` | operational (reference) | read by every package (`DECODE`/status lookups); written only by seed scripts | PROPOSED |
| `PLANS` | operational (reference) | read by `pkg_plans`, `pkg_rating`; seed-written only | PROPOSED |
| `USAGE_EVENTS` | operational (reference/feed) | read by `pkg_rating`; trigger `trg_usage_events_check`; written by the app/seeder, not by packages | PROPOSED |
| `CUSTOMER_MASTER` | operational (reference) | triggers `trg_customer_master_seq`, `trg_customer_master_hist`; app-written, package-read | PROPOSED |
| `ENTITY_ATTR_VALUE` | operational (reference) | trigger `trg_entity_attr_value_seq`; app-written EAV | PROPOSED |
| `SUBSCRIPTIONS_HIST` | analytical | trigger-maintained full-row history of `SUBSCRIPTIONS`; read by reports only | PROPOSED |
| `CUSTOMER_MASTER_HIST` | analytical | trigger-maintained full-row history of `CUSTOMER_MASTER`; read by reports only | PROPOSED |
| `INVOICE_HEADER` | analytical | legacy reporting copy; no package writes; bulk seeded | PROPOSED |
| `INVOICE_LINE` | analytical | legacy reporting copy (37 planted orphans -> quarantine); no package writes | PROPOSED |
| `FIXTURE_META` | excluded | fixture marker, not business data | PROPOSED |

Analytical-track units run the warehouse family defaults (`11-front_door_warehouse.md`); both tracks
share this ledger, `04_dependency_register.md` and one STOP sequence.

## Data-load posture

| Track | Posture | Mark |
|---|---|---|
| operational | CDC coexistence: Debezium (Oracle LogMiner) -> Kafka -> Delta landing (`ow_tp.bronze`) -> Lakebase apply. Gated on D10-1 (supplemental logging + `c##dbzuser`) and D10-3 (Debezium/Kafka footprint). Rehearsal fallback: SCN-pinned freeze-and-load into the Lakebase branch. | FACT |
| analytical | SCN-pinned freeze-and-load (`AS OF SCN`) into Delta | FACT |
| coexistence read bridge | Lakehouse Federation / JDBC to Oracle approved; blocked until D10-2 (serverless egress CIDRs added to the SG). Recon from Devin VMs works now. | FACT |
| lakehouse sync | operational tables synced from Lakebase into `ow_tp.silver` for the analytical track (Lakebase -> UC) | PROPOSED |

## Family defaults (OLTP front door)

- Unit = table group + its constraints, triggers, sequences + the procedures that write it; a procedure and the tables it mutates are never split.
- Lineage = package write-sets + FK graph + application connection census (D4).
- Dominant surfaces: SQL profile + LAKEBASE profile; analytical units use SQL/PIPELINE.
- Conversion target: Lakebase Postgres 17 (PL/pgSQL, native sequences/identities, Postgres constraints) for operational; DBSQL/Delta for analytical.
- Application repoint is the single routing point at STOP E; the customer holds the cutover principal.
- Dialect skill: `oracle-plsql` (installed, `skills/oracle-plsql/SKILL.md`) + `target-routing` -> `databricks-lakebase`, `databricks-core`, `databricks-dbsql`, `databricks-jobs`, `databricks-dabs`.

## Process

| Field | Value | Mark |
|---|---|---|
| Fan-out width | 4 children per wave; pilot wave <= 4 | FACT |
| Circuit breaker | 3 same-class failures | FACT |
| Wave order | dependency-ordered bronze -> silver -> gold | FACT |
| Preflight | `factory-doctor` before every wave; `migration-fanout` for every multi-batch wave | FACT |
| Cutover principal | customer-held, never provisioned to Devin; Devin prepares the repoint PR, customer executes | FACT |
| Large-wave threshold | 10 batches (never reached at width 4) | PROPOSED |
