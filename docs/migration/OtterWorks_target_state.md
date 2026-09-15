# OtterWorks billing estate — target state

What "migrated" means for this engagement. Every field is FACT (cited) or PROPOSED
(default, confirmed at STOP A via the intake). Children read this plus their surface
profile and nothing else.

Intake: `.migration/00_intake.md`. Run branch: `tp-run/databricks-20260915T045714Z`.

---

## CORE (applies to everything)

| Field | Value | Status |
|---|---|---|
| Workspace | `DATABRICKS_DEMO_HOST` | FACT (intake) |
| Identity | service principal `dhrov_spa`, OAuth M2M (`DATABRICKS_CLIENT_ID`/`_SECRET`) | FACT (probe) |
| Catalog | `ow_tp` — the only catalog any migration write may touch | FACT (intake) |
| Schemas | `bronze` (landing + raw CDC), `silver` (conformed), `gold` (reporting, metric views) | FACT (intake) |
| Volume | `/Volumes/ow_tp/bronze/landing` | FACT (probe) |
| Naming | every object, job, pipeline, secret scope and Lakebase resource prefixed `ow_tp` / `ow-tp-` | FACT (intake) |
| Compute | existing serverless SQL warehouse `565cd2fd713738c4`; serverless for jobs and pipelines; **no new clusters** | FACT (intake) |
| Code language | SQL for set-based logic and reporting; PySpark where the logic is row-wise, stateful, or file-parsing | PROPOSED |
| Repo layout | TARGET and DOCS are both this repo. Migrated code under `databricks/`, artifacts under `.migration/` and `docs/migration/` | PROPOSED |
| Deployment | Declarative Automation Bundle (DAB), target `migration`. `prod`/`production` targets are denied by the guard | PROPOSED |
| Secrets | referenced by name only, from scope `ow_tp` or the session environment. Never inlined, never committed | FACT (guardrail) |
| Schedules | every migrated schedule lands **PAUSED**. Unpausing is a cutover action | FACT (guardrail) |
| CI gate | `make tp-smoke` plus the unit's own recon verdict | FACT (repo) |

**Drift rules — a PR is rejected on any of these:** a write outside `ow_tp`; a hard-coded
credential, host, or warehouse id; an unpaused schedule; a new cluster; a DDL statement
against a shared table from a child; an object without the `ow_tp` prefix; a recon verdict
that is absent, stale, or fixture-mode.

---

## SQL — PL/SQL packages, views, report queries

| Field | Value | Status |
|---|---|---|
| Dialect source | Oracle PL/SQL; `oracle-plsql` skill owns the conversion rules and `canonicalization.json` | FACT |
| Analytical target | Databricks SQL. Set logic replaces cursor loops; no row-at-a-time rewrite in Spark | PROPOSED |
| Operational target | Lakebase Postgres 17 PL/pgSQL for procedures the billing application calls transactionally | FACT (front-door split) |
| Materialization | view for thin projections, table for anything a job writes, MV only where refresh cost is justified | PROPOSED |
| Dates | `VARCHAR2(9)` `DD-MON-YY` strings parse to `DATE`. Unparseable values go to the declared anomaly set, never to NULL silently | FACT (intake) |
| Money | `NUMBER(12,2)` → `DECIMAL(12,2)`. Never `DOUBLE` | FACT (intake) |
| Package state | `pkg_*` globals become explicit parameters or a state table; never a session global | PROPOSED |
| Swallowed errors | `EXCEPTION WHEN OTHERS THEN NULL` is **not** reproduced. Errors surface and are recorded; the behavior change is declared per unit | PROPOSED |

**Drift rules:** a cursor loop carried over as a loop; money in a float type; a date parsed
with a silent fallback; a `WHEN OTHERS` swallow; business logic left in a trigger.

---

## PIPELINE — CUSTBILL close, analytics jobs, CDC ingest

| Field | Value | Status |
|---|---|---|
| Runtime | Lakeflow Spark Declarative Pipelines for ingest/transform chains; Lakeflow Jobs tasks for scripted steps | FACT (intake) |
| Layering | bronze = raw as landed (incl. CDC), silver = conformed and typed, gold = reporting | FACT (intake) |
| Load pattern | materialize everything. Debezium initial snapshot seeds CDC tables; chunked restart-safe JDBC backfill for the rest (`backfill-planner`) | FACT (intake) |
| Reject rows | expectations with a **quarantine table** per pipeline; never `DROP ROW` silently. Quarantine rate is a graded metric | FACT (intake) |
| Restart | every pipeline idempotent and restart-safe; no lock files, no `sleep` as a dependency | FACT (repo pain point) |
| CDC apply | AUTO CDC into Delta history (SCD-2) from Kinesis; Debezium Server on the existing `otterworks-dev` EKS cluster | FACT (intake) |
| Parsing | fixed-width parsing moves into the pipeline with a declared schema and a trailer-count check the legacy chain never had | PROPOSED |
| Output contracts | the finance report is a real spreadsheet or a Delta table consumers query — not a CSV renamed `.xls`, and not emailed through sendmail | PROPOSED |

**Drift rules:** a pipeline that drops bad rows without quarantining; a load that cannot
resume; a hand-rolled retry loop where the job's retry policy belongs; parsing without a
declared schema.

---

## ORCHESTRATION

| Field | Value | Status |
|---|---|---|
| Scheduler | Lakeflow Jobs. Cron and DBMS_SCHEDULER are retired, not wrapped | FACT (intake) |
| Dependencies | task-level `depends_on`. No `sleep`, no lock files, no size-check completion probes | FACT (intake) |
| Retries | per-task retry policy with backoff; failure is loud | FACT (intake) |
| Schedules | created PAUSED; the legacy job keeps running until cutover | FACT (guardrail) |
| Alerting | job-level failure notification to `#ow-migrations` | PROPOSED |

**Drift rules:** an unpaused schedule; a task that swallows a non-zero exit; a dependency
expressed as a wait.

---

## CONSUMER

| Field | Value | Status |
|---|---|---|
| Billing application | repoints to Lakebase Postgres at cutover, by the cutover principal, never by Devin | FACT (intake) |
| Finance close output | rebuilt as a gold table plus an AI/BI dashboard; the sendmail path is not reproduced | PROPOSED |
| Analytics consumers | read `ow_tp.gold` via the serverless warehouse | PROPOSED |
| Cutover SLA | one close cycle of parallel run before any consumer moves | PROPOSED |

**Drift rules:** a consumer repointed from a child session; a dashboard built on `bronze`.

---

## LAKEBASE — operational track

| Field | Value | Status |
|---|---|---|
| Project | `ow-tp-billing` (Autoscaling Postgres, `databricks postgres`) | FACT (intake) |
| Branches | one `mig-*` branch per wave batch, TTL'd. `production` is never written from a migration session | FACT (guardrail) |
| Database / schema | `ow_tp` / `billing` | FACT (intake) |
| Scope | tables, constraints, sequences, indexes and procedures the billing application writes transactionally: `TENANTS`, `SUBSCRIPTIONS`, `CUSTOMER_MASTER` (+ EAV overflow), `PLANS`, `INVOICES`, `INVOICE_LINES`, `CREDIT_NOTES`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS`, `USAGE_EVENTS` | PROPOSED |
| Out of scope (→ Delta) | `*_HIST` twins, `BILLING_AUDIT_LOG`, `RATING_PERIODS`, `RATING_RESULTS`, and every reporting surface | PROPOSED |
| Identities | Oracle sequence+trigger pairs become Postgres sequences/identity columns; trigger-side business logic moves to the application or a procedure | PROPOSED |
| Sync | operational tables sync into Unity Catalog for the analytical track; warehouse-mastered reference data syncs back as synced tables | PROPOSED |
| Connectivity | OAuth token refresh, pooled, SSL required | PROPOSED |
| Compute | scale-to-zero on non-production branches | PROPOSED |

**Drift rules:** a write to the `production` branch; a branch without a TTL; an operational
table that also exists as a Delta write target (that is a write-target collision, and a halt).

---

## ML-SCORING

In scope, but only for the post-pipeline-1 build session that adds the dunning-risk score —
not for any migration unit, because the legacy estate has no scoring job to reconcile
against. Prediction-parity tolerance is therefore N/A; the score is new work graded on its
own acceptance criteria and synced back to Lakebase.

---

## DATA / DEPENDENCY

| Field | Value | Status |
|---|---|---|
| Coexistence mechanism | **Lakehouse Federation to Oracle**, read-only, `--family databricks` for recon. Required because the harness refuses the untested Oracle source adapter. Gated on the security-group change (D10-01) | PROPOSED — decision pending |
| Fallback if federation is refused | JDBC extract to `bronze` + snapshot-mode recon, explicitly DEGRADED, with snapshot manifests per unit | PROPOSED |
| CDC | Debezium Server (EKS) → Kinesis on-demand → Lakeflow AUTO CDC. Source-side prerequisites are complete: ARCHIVELOG, ALL COLUMN supplemental logging on 19 tables, `C##DBZUSER` | FACT (probe + approved DDL) |
| Source writes | one, ever: the approved supplemental-log DDL. Oracle is read-only in every other respect | FACT (decision D-001) |
| PII | demo estate, no masking requirement | PROPOSED |
| Decommission | Oracle stays up through parallel run; decommission is out of scope for this run | PROPOSED |
