# OW_BILLING estate inventory (STOP B input)

Estate: Oracle Database Free 23ai, PDB `FREEPDB1`, schema `OW_BILLING` (`52.201.36.9:1521`, read-only principal `ORACLE_OW_BILLING_RO_DSN`).
Census taken 2026-09-14 at `CURRENT_SCN` 2149687-2149771 with `DBA_*` queries only (`.migration/evidence/census/oracle_census.py`; raw results in `.migration/evidence/census/*.tsv`). Consumer census from the OtterWorks repository (`.migration/evidence/census/d4_consumer_census.md`). Every row is FACT unless marked INFERRED or PROPOSED. Breadth only: no object internals were analysed and nothing was converted.

## 1. Census

Object types (`DBA_OBJECTS`, all 69 `VALID`): 20 tables, 25 indexes, 5 packages, 5 package bodies, 7 triggers, 5 sequences, 2 scheduler jobs. Constraints (`DBA_CONSTRAINTS`, 116): 19 PK, 6 UK, 13 FK, 78 CHECK. Views/mviews/synonyms/LOBs/identity columns: 0. Statistics are not gathered on any table (`NUM_ROWS` null), so row counts below are live `COUNT(*)` inside one `SET TRANSACTION READ ONLY` snapshot.

### 1.1 Tables

| Table | Track | Rows | Cols | Idx | Trg | FK parents | Pipeline | Complexity signal |
|---|---|---|---|---|---|---|---|---|
| TENANTS | operational | 69 | 8 | 1 | 0 | - | P1 (shared root) | 6 child FKs |
| PLANS | operational (reference) | 3 | 7 | 1 | 0 | - | P1 (shared) | reference |
| CODES | operational (reference) | 32 | 5 | 1 | 0 | - | P1 (shared) | reference; trigger lookup |
| SUBSCRIPTIONS | operational | 69 | 9 | 2 | 2 | TENANTS, PLANS | P1 (shared with P2) | 2 triggers, 2 FK, written by 3 packages |
| USAGE_EVENTS | operational | 814 | 7 | 2 | 1 | TENANTS | P1 | feed table, check trigger |
| RATING_PERIODS | operational | 3 | 6 | 1 | 0 | TENANTS | P1 | |
| RATING_RESULTS | operational | 3 | 7 | 1 | 0 | RATING_PERIODS, SUBSCRIPTIONS | P1 | |
| INVOICES | operational | 3 | 10 | 2 | 0 | TENANTS, RATING_PERIODS | P1 (shared with P2) | money |
| INVOICE_LINES | operational | 2 | 7 | 1 | 0 | INVOICES | P1 | money |
| CREDIT_NOTES | operational | 5 | 7 | 1 | 0 | TENANTS | P1 | money |
| BILLING_AUDIT_LOG | operational | 0 | 5 | 1 | 1 | - | shared (all) | sequence trigger, purge job |
| SUBSCRIPTIONS_HIST | analytical | 0 | 10 | 1 | 0 | - | P1 (trigger output) | trigger-fed |
| DUNNING_ATTEMPTS | operational | 1 | 7 | 2 | 0 | TENANTS, INVOICES | P2 | |
| NOTIFICATIONS | operational | 1 | 7 | 1 | 0 | TENANTS | P2 | |
| CUSTOMER_MASTER | operational (reference) | 25,000 | 43 | 3 | 2 | - | P3 | 43 cols, 2 triggers, EAV parent |
| ENTITY_ATTR_VALUE | operational (reference) | 8,333 | 8 | 2 | 1 | - | P3 | EAV, sequence trigger |
| CUSTOMER_MASTER_HIST | analytical | 0 | 45 | 1 | 0 | - | P3 (trigger output) | trigger-fed |
| INVOICE_HEADER | analytical | 18,750 | 14 | 1 | 0 | - | P3 | legacy reporting copy; report consumer |
| INVOICE_LINE | analytical | 150,000 | 15 | 1 | 0 | - | P3 | 37 orphan rows (no FK); report consumer |
| FIXTURE_META | excluded | 1 | 4 | 1 | 0 | - | excluded | environment metadata table, not business data |

Total columns 432; indexes 25 (all attached to a table above and inherit its pipeline).

### 1.2 Code and schedule objects

| Object | Type | Lines (spec+body) | Routines | Writes (FACT, `DBA_SOURCE`) | Reads (FACT, `DBA_DEPENDENCIES`) | Pipeline |
|---|---|---|---|---|---|---|
| PKG_RATING | package | 213 | 4 | RATING_PERIODS, RATING_RESULTS | PLANS, SUBSCRIPTIONS, USAGE_EVENTS, PKG_OW_UTIL | P1 |
| PKG_INVOICING | package | 190 | 4 | INVOICES, INVOICE_LINES, CREDIT_NOTES | PLANS, SUBSCRIPTIONS, TENANTS, PKG_RATING, PKG_OW_UTIL | P1 |
| PKG_PLANS | package | 101 | 3 | SUBSCRIPTIONS | PLANS, TENANTS, PKG_OW_UTIL | P1 |
| PKG_DUNNING | package | 95 | 3 | DUNNING_ATTEMPTS, NOTIFICATIONS, SUBSCRIPTIONS, TENANTS | INVOICES, PKG_OW_UTIL | P2 |
| PKG_OW_UTIL | package | 72 | 5 | BILLING_AUDIT_LOG | - | shared (all) |
| TRG_SUBSCRIPTIONS_HIST | trigger AFTER UPD/DEL | 18 | | SUBSCRIPTIONS_HIST (SEQ_SUBSCRIPTIONS_HIST) | SUBSCRIPTIONS | P1 |
| TRG_SUB_NO_UNCANCEL | trigger BEFORE UPD | 8 | | raises | SUBSCRIPTIONS | P1 |
| TRG_USAGE_EVENTS_CHECK | trigger BEFORE INS | 15 | | raises | USAGE_EVENTS, CODES | P1 |
| TRG_BILLING_AUDIT_LOG_ID | trigger BEFORE INS | 8 | | BILLING_AUDIT_LOG.id (SEQ_BILLING_AUDIT_LOG) | | shared |
| TRG_CUSTOMER_MASTER_HIST | trigger AFTER UPD/DEL | 16 | | CUSTOMER_MASTER_HIST (SEQ_CUSTOMER_MASTER_HIST) | CUSTOMER_MASTER | P3 |
| TRG_CUSTOMER_MASTER_SEQ | trigger BEFORE INS | 10 | | CUSTOMER_MASTER.id (SEQ_CUSTOMER_MASTER) | | P3 |
| TRG_ENTITY_ATTR_VALUE_SEQ | trigger BEFORE INS | 8 | | ENTITY_ATTR_VALUE.id (SEQ_ENTITY_ATTR_VALUE) | | P3 |
| SEQ_BILLING_AUDIT_LOG / SEQ_SUBSCRIPTIONS_HIST | sequence (last 1 / 1, nocache) | | | | | shared / P1 |
| SEQ_CUSTOMER_MASTER (last 125,000) / SEQ_CUSTOMER_MASTER_HIST (1) / SEQ_ENTITY_ATTR_VALUE (11,001, cache 1000) | sequence | | | | | P3 |
| JOB_NIGHTLY_DUNNING | DBMS_SCHEDULER, DISABLED, daily 02:00, never run | | | calls PKG_DUNNING.sp_schedule_dunning + sp_suspend_overdue | | P2 |
| JOB_PURGE_AUDIT_LOG | DBMS_SCHEDULER, DISABLED, daily 03:30, never run | | | DELETE BILLING_AUDIT_LOG > 90 days | | shared |

Last-modified evidence: every object has `CREATED = LAST_DDL_TIME = 2026-09-14` (schema deployed as one unit); scheduler `RUN_COUNT = 0` for both jobs. There is no query-history or audit-trail source for "last run" of packages (unified audit has only Oracle defaults), so per-routine last-run is UNVERIFIABLE; application call paths are taken from the consumer census instead.

## 2. Lineage

Edges are in `.migration/evidence/census/lineage_edges.tsv` (55 edges; 49 FACT from `DBA_DEPENDENCIES`, `DBA_CONSTRAINTS`, `DBA_TRIGGERS`, `DBA_SCHEDULER_JOBS` and the `DBA_SOURCE` write-statement scan; 6 INFERRED consumer edges). Rendered: `docs/migration/OW_BILLING_lineage_dag.png`.

Depth (longest FK/write path): TENANTS -> SUBSCRIPTIONS -> RATING_RESULTS / RATING_PERIODS -> INVOICES -> INVOICE_LINES -> DUNNING_ATTEMPTS = 5 table hops; package call chain PKG_OW_UTIL -> PKG_RATING -> PKG_INVOICING = 3.

### 2.1 Consumers (D4, from repository census)

| Consumer | Kind | Touches | Mode | Mark |
|---|---|---|---|---|
| `services/legacy-billing/app/reports.py` (+ Flask app, admin-dashboard billing-report page) | application report endpoint | INVOICE_HEADER, INVOICE_LINE, CODES, CUSTOMER_MASTER | read via `oracledb`, `ORACLE_*` env | FACT (code) |
| `procs/harness/oracle_record.py` + `procs/oracle/oracle_map.yaml` | parity harness (test) | calls PKG_PLANS, PKG_RATING, PKG_INVOICING, PKG_DUNNING, PKG_OW_UTIL; resets operational tables | read/write | FACT (code) |
| `testdata/legacy/oracle_billing_seed.py` | seeder (batch) | 16 tables | write | FACT (code); not a production consumer |
| `scripts/tp_pain/mongodb.py` | inspection report | CUSTOMER_MASTER, CUSTOMER_MASTER_HIST, ENTITY_ATTR_VALUE | read | FACT (code) |
| Billing application transaction path (plan change, rating, invoicing) | application | PKG_PLANS / PKG_RATING / PKG_INVOICING | call | INFERRED: no service in the repo holds an Oracle connection pool for these packages; the only live callers found are the parity harness and the disabled scheduler job |
| CUSTBILL batch chain (`etl/legacy-extra/`) | batch | none: file-based (SFTP -> fixed-width -> PSV -> report) | - | FACT: no Oracle access; the intake's "CUSTBILL outputs" are not fed from OW_BILLING |

## 3. Pipelines

| Pipeline | Objects (excl. indexes) | Complexity (PL/SQL lines / routines / triggers / FK depth) | Lineage depth | Upstream | Downstream | Difficulty rank |
|---|---|---|---|---|---|---|
| **P1 Monthly invoicing** (rating -> invoicing, plans): PKG_RATING, PKG_INVOICING, PKG_PLANS; tables USAGE_EVENTS, RATING_PERIODS, RATING_RESULTS, INVOICES, INVOICE_LINES, CREDIT_NOTES, SUBSCRIPTIONS, SUBSCRIPTIONS_HIST; triggers TRG_SUBSCRIPTIONS_HIST, TRG_SUB_NO_UNCANCEL, TRG_USAGE_EVENTS_CHECK; SEQ_SUBSCRIPTIONS_HIST | 18 | 504 lines / 11 routines / 3 triggers / depth 4 | 4 | shared root tables | P2 (INVOICES, SUBSCRIPTIONS) | 1 (hardest: money, 3 packages, trigger side effects, transactional) |
| **P2 Dunning and notifications**: PKG_DUNNING, DUNNING_ATTEMPTS, NOTIFICATIONS, JOB_NIGHTLY_DUNNING | 5 | 95 / 3 / 0 / depth 1 | 1 (+P1) | P1 (INVOICES, SUBSCRIPTIONS, TENANTS) | none | 3 |
| **P3 Customer master and legacy reporting copies**: CUSTOMER_MASTER, ENTITY_ATTR_VALUE, CUSTOMER_MASTER_HIST, INVOICE_HEADER, INVOICE_LINE; TRG_CUSTOMER_MASTER_HIST, TRG_CUSTOMER_MASTER_SEQ, TRG_ENTITY_ATTR_VALUE_SEQ; SEQ_CUSTOMER_MASTER, SEQ_CUSTOMER_MASTER_HIST, SEQ_ENTITY_ATTR_VALUE | 11 | 34 trigger lines / 0 routines / 3 triggers / depth 1; volume 202k rows, 37 orphans, EAV | 1 | none (no FK to the billing core) | report endpoint (D4) | 2 (volumetric + dirty data, not procedural) |
| **Shared set**: TENANTS, PLANS, CODES, BILLING_AUDIT_LOG, PKG_OW_UTIL (spec+body), TRG_BILLING_AUDIT_LOG_ID, SEQ_BILLING_AUDIT_LOG, JOB_PURGE_AUDIT_LOG | 9 | 72 / 5 / 1 | 0 | none | P1, P2, P3 | wave 0 |
| **Confirmed exclusion**: FIXTURE_META | 1 | | | | | |

P1 = the parent's "Pipeline 1 = Monthly invoicing". P2 and P3 are the parent's pipelines 2 and 3 and share this ledger.

## 4. Coverage proof

Non-index objects: 20 tables + 10 package objects (5 specs + 5 bodies) + 7 triggers + 5 sequences + 2 jobs = 44.

| Type | P1 | P2 | P3 | Shared | Excluded | Total |
|---|---|---|---|---|---|---|
| Tables | 8 | 2 | 5 | 4 | 1 | 20 |
| Package spec+body | 6 | 2 | 0 | 2 | 0 | 10 |
| Triggers | 3 | 0 | 3 | 1 | 0 | 7 |
| Sequences | 1 | 0 | 3 | 1 | 0 | 5 |
| Scheduler jobs | 0 | 1 | 0 | 1 | 0 | 2 |
| **Sum** | 18 | 5 | 11 | 9 | 1 | **44** |

Every object is in exactly one set. The 25 indexes and 116 constraints follow their table (`indexes.tsv`, `constraints.tsv`).

PROPOSED-unused: none dropped. Candidates flagged for STOP C, not removed: `JOB_NIGHTLY_DUNNING` and `JOB_PURGE_AUDIT_LOG` (DISABLED, never run), `CUSTOMER_MASTER_HIST` and `SUBSCRIPTIONS_HIST` (0 rows, trigger-fed), `BILLING_AUDIT_LOG` (0 rows). They carry live code paths and are migrated with their pipeline.

External cross-check: intake stated 19 tables + FIXTURE_META, 5 packages / 19 routines, 7 triggers, 5 sequences, 2 jobs: census matches exactly (19 routines in `DBA_PROCEDURES`). Static repository DDL (`services/legacy-billing/db/oracle/schema`, `packages`) matches the live object list. Seeded counts match intake (25,000 / 18,750 / 150,000 / 8,333; 60 demo tenants of 69). Completeness: VERIFIED against two independent counts.

## 5. Shared-object map

| Object | Used by | Proposed owner | Note |
|---|---|---|---|
| TENANTS | P1 (write via PKG_DUNNING only in P2; FK root for 6 tables), P2, P3 report join (INFERRED) | wave 0 shared, Lakebase | PKG_DUNNING updates TENANTS (D6-1) |
| SUBSCRIPTIONS | P1 (PKG_PLANS, PKG_RATING read, TRG_*), P2 (PKG_DUNNING update) | P1 | two writers across pipelines (D6-2) |
| INVOICES | P1 (PKG_INVOICING), P2 (PKG_DUNNING read, DUNNING_ATTEMPTS FK) | P1 | |
| PLANS, CODES | P1 packages/trigger; CODES also the report endpoint (P3) | wave 0 shared | reference; CODES needed in both Lakebase and Delta (synced) |
| PKG_OW_UTIL, BILLING_AUDIT_LOG, TRG_BILLING_AUDIT_LOG_ID, SEQ_BILLING_AUDIT_LOG, JOB_PURGE_AUDIT_LOG | every package | wave 0 shared | utility + audit log |
| CUSTOMER_MASTER | P3 owner; report endpoint; `tp_pain` inspection | P3 | no FK from billing core (tenant/customer join is by convention, INFERRED) |

## 6. Governance

See `.migration/08_governance_inventory.md`: 4 non-Oracle-maintained principals, 20 system-privilege rows, 3 role rows, 0 object grants, 0 VPD/redaction policies, ALL COLUMN supplemental logging on the 10 operational tables (confirms D10-1 closure). New finding D10-8: the read-only principal lacks `FLASHBACK ANY TABLE`, so `AS OF SCN` reads fail (ORA-41900).

## 7. Parallelism

Depth 0 (shared roots, wave 0): TENANTS, PLANS, CODES, BILLING_AUDIT_LOG + PKG_OW_UTIL: 1 batch, serial. Depth 1: SUBSCRIPTIONS(+hist, PKG_PLANS), USAGE_EVENTS, CUSTOMER_MASTER/EAV(+hist), INVOICE_HEADER/INVOICE_LINE: width 4. Depth 2: RATING_PERIODS/RATING_RESULTS + PKG_RATING: width 1. Depth 3: INVOICES/INVOICE_LINES/CREDIT_NOTES + PKG_INVOICING: width 1. Depth 4: DUNNING_ATTEMPTS/NOTIFICATIONS + PKG_DUNNING + job: width 1. Serial floor = 5 waves; max width 4 = the D10 fan-out limit, so no wave is throttled. P1 alone: serial floor 4 (wave 0, subscriptions/usage, rating, invoicing), width <= 2.

## 8. First-pass dependencies added to the register

D10-8 (FLASHBACK privilege), D4-2 (report endpoint), D4-3 (parity harness), D4-4 (customer-master inspection), D6-1/D6-2 (cross-pipeline writers on TENANTS, SUBSCRIPTIONS), D3-1 (USAGE_EVENTS feed producer unknown), D7-1 (NOTIFICATIONS hand-off), D9-1 (sequence/identity contracts), D2-2 (CODES dual-track). All UNDECIDED; see `.migration/04_dependency_register.md`.
