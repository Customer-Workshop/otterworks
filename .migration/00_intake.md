# Migration intake — OtterWorks billing estate → Databricks

Run: `tp-run/databricks-<timestamp>` (branch not yet cut)
Repo: Cognition-Partner-Workshops/otterworks, off `tech-partnerships`
Owner: dhrov.subramanian
Date: 2026-09-15

---

## 1. Source estate

### Oracle (verified live, not read from the repo)

| Fact | Value |
|---|---|
| Engine | Oracle AI Database 26ai Free, 23.26.3.0.0 |
| Host | `ow-tp-oracle`, i-0be201ad6412c5e5e, t3.large, 52.201.36.9:1521 |
| Service / PDB | FREEPDB1 |
| Schema | OW_BILLING |
| Log mode | ARCHIVELOG, minimal supplemental logging ON |

Objects in OW_BILLING:

| Type | Count |
|---|---|
| Tables | 20 |
| Indexes | 25 |
| Packages (+ bodies) | 5 + 5 |
| Sequences | 5 |
| Triggers | 7 |
| DBMS_SCHEDULER jobs | 2 (both DISABLED) |

Packages: `pkg_ow_util`, `pkg_plans`, `pkg_rating`, `pkg_invoicing`, `pkg_dunning`.
Jobs: `JOB_NIGHTLY_DUNNING`, `JOB_PURGE_AUDIT_LOG`.
Volume: `CUSTOMER_MASTER` = 25,000 rows.

Known characteristics carried into the correctness contract: 155-column `CUSTOMER_MASTER`,
`ENTITY_ATTR_VALUE` EAV overflow, `VARCHAR2(9)` `DD-MON-YY` date strings, sequence+trigger
keys, package-state globals, cursor-loop rating/invoicing/dunning, autonomous-transaction
logging, `EXCEPTION WHEN OTHERS THEN NULL` in the dunning and purge jobs, orphan invoice
lines, dirty signup-date strings, malformed CSV lists.

### CUSTBILL finance-close chain

`etl/legacy-extra/jobs/sftp_ingest_poll.ksh`, `parse_custbill_fixedwidth.sh`,
`finance_excel_report.pl`, `run_all.sh`. Cron-scheduled, overlapping windows, `sleep 600`
as dependency management, lock files not cleared on crash, size-check instead of an atomic
completion protocol, no parser validation or quarantine, no trailer-count reconciliation,
CSV renamed `.xls` and mailed through a sendmail pipe that no longer delivers.

### Product analytics

Five Python cron jobs (`analytics_daily.py`, `audit_archive_weekly.py`,
`search_reindex_weekly.py`, `storage_cleanup_daily.py`, `user_activity_daily.py`) plus the
Scala `UsageRollupJob` and its aggregator/repository classes. Credentials in plaintext
`etl/config.ini`.

---

## 2. Target

Workspace: `DATABRICKS_DEMO_HOST` (shared demo workspace).

| Surface | Target |
|---|---|
| Delta history / reporting / analytics | catalog `ow_tp`, schemas `bronze`, `silver`, `gold` |
| Operational writes (billing app) | Lakebase Postgres, new project `ow-tp-billing`, schema `billing`, `mig-*` branch per batch |
| Landing | `/Volumes/ow_tp/bronze/landing` |
| Compute | existing serverless SQL warehouse; no new clusters |
| Naming | everything prefixed `ow_tp` / `ow-tp-`; jobs `ow_tp_*`; secret scope `ow_tp` |

Pipeline shapes:

1. **Monthly invoicing (Oracle).** Lakebase OLTP front door for application writes, Delta for
   history and reporting — plus a CDC leg (see §3): Debezium Server on the existing
   `otterworks-dev` EKS cluster → Kinesis on-demand → Lakeflow pipeline using AUTO CDC into
   Delta history.
2. **Finance close (CUSTBILL).** Lakeflow pipeline with expectations and a quarantine table;
   Lakeflow Job replaces cron.
3. **Product analytics.** Lakeflow Jobs with task dependencies and retries, SQL on Delta,
   secrets referenced by name.

Post-pipeline-1 build sessions (three, in parallel): per-tenant usage meter into Lakebase;
finance gold layer with metric views (ARR, MRR by plan, AR ageing, overage, storage cost per
tenant) plus an AI/BI dashboard; dunning-risk score synced back to Lakebase.

---

## 3. Access

| Purpose | Secret | Notes |
|---|---|---|
| Oracle read-only | `ow-tp/oracle/ow_billing_ro` (AWS Secrets Manager) | verified: connects, `CREATE TABLE` fails ORA-01031 |
| Oracle admin (one step only) | `ow-tp/oracle/admin` | used **only** for the approved supplemental-log DDL |
| Oracle CDC capture | `ow-tp/oracle/dbzuser` (`C##DBZUSER`) | LOGMINING, SELECT ANY TRANSACTION/TABLE, FLASHBACK ANY TABLE, SET CONTAINER |
| Databricks | `DATABRICKS_DEMO_HOST` / `DATABRICKS_DEMO_TOKEN` | PAT, files scope verified |
| Lakebase | `OW_TP_LAKEBASE_DSN` | to be created with project `ow-tp-billing` |
| AWS | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | account 599083837640, us-east-1 |

**Federation/JDBC.** No Lakehouse Federation. SG `sg-0eaf11f4434260e1e` opens 1521 only to
Devin egress CIDRs; Databricks serverless cannot reach it and we are not opening it. Oracle
is read over JDBC from migration sessions, landing extracts to the bronze volume.

**Recorded override — CDC on Oracle.** The standing rule is that the source is read-only and
CDC is never enabled by Devin. dhrov.subramanian explicitly overrode this on 2026-09-15
("wire CDC into pipeline 1 from start and approved, touch oracle and enable CDC"). Scope of
the override:

- One write to Oracle, ever: `ALTER TABLE ... ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS` on the
  ten OW_BILLING tables that lack it, including `CUSTOMER_MASTER`. Run once at preflight
  under the admin credential, logged, and never repeated.
- Ten tables already carry ALL COLUMN LOGGING: `TENANTS`, `SUBSCRIPTIONS`, `RATING_PERIODS`,
  `RATING_RESULTS`, `INVOICES`, `INVOICE_LINES`, `CREDIT_NOTES`, `DUNNING_ATTEMPTS`,
  `NOTIFICATIONS`, `BILLING_AUDIT_LOG`.
- Archive-log housekeeping added at the same time; supplemental logging raises redo volume and
  archive logs sit on the instance root volume.
- No other Oracle change. No schema edits, no job changes, no data writes.
- The factory's pre-tool guard will block the DDL; this override is recorded in
  `.migration/06_decisions.md` as the authorization.

Risk accepted: Debezium's LogMiner connector against 26ai Free is outside the commonly tested
matrix. Fallback if it will not run: pipeline 1 reconciles on JDBC + watermarks while the CDC
leg is fixed alongside, so STOP E is not blocked by it.

---

## 4. Correctness contract

Reconciliation mode: **aggregate + row-level fingerprint**, both tiers, every unit.

| Class | Tolerance |
|---|---|
| Money (`NUMBER(12,2)`) | exact, zero tolerance |
| Row counts | exact, zero tolerance |
| Other floats | 1e-9 relative |
| Dates | canonicalized to ISO before comparison |
| Unparseable date strings | compared as a declared anomaly set |
| Known anomalies (orphan invoice lines, malformed CSV lists) | compared as sets — must be reproduced, not cleaned |

Recon must be recomputed from the target platform, prove idempotency by rerun, and list
unverified paths explicitly. Tolerances are frozen; changing them mid-run requires a recorded
decision from the owner. The harness verdict is the merge authority — no accelerator or tool
output self-certifies.

Circuit breaker: halt the wave after 3 same-class failures. Children cap at 3 recon re-runs.

---

## 5. Process

| Item | Decision |
|---|---|
| Working branch | `make tp-run-branch TRACK=databricks` → `tp-run/databricks-<ts>` off `tech-partnerships` |
| PR target | the working branch only, never `tech-partnerships`; one PR per unit, never a stack |
| Pipeline order | strictly sequential; pipeline N+1 starts only when pipeline N is parked at STOP E |
| Build sessions | three, in parallel, after pipeline 1 reconciles |
| Fan-out width | pilot 3, then 5 |
| Data-load posture | materialize everything — Debezium initial snapshot for CDC tables, chunked restart-safe JDBC backfill for the rest |
| Stop routing | this web session (decisions) + mirrored to Slack `#ow-migrations` (visibility) |
| Notifications | only at a blocking stop, a wave close, or a halt — one message each |
| Cutover principal | held by dhrov.subramanian; Devin never holds or requests it |
| STOP E | always a human decision; the parent never approves it |

Safety invariants: no DDL on shared tables from a child; children write only their assigned
namespace slice and never edit `.migration/`; a write-target collision or undeclared target is
a halt, not a fix; production is never repointed by Devin; secrets are referenced by name only.
