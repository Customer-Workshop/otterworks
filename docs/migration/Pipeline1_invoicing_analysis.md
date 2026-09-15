# Pipeline 1 — monthly invoicing (Oracle `OW_BILLING`) — analysis

Scope pinned at STOP B: the 63 pipeline-1 objects from `OtterWorks_inventory.md` §3.
Targets: Lakebase Postgres (`ow-tp-billing`, database `ow_tp`, schema `billing`) for what
the billing application writes; Delta (`ow_tp.bronze/silver/gold`) for history and
reporting. Analysis only — no plan, no code, no children.

Cites are file:line on this branch, or FACT(live) for the Oracle dictionary.

---

## 1. Pinned scope

Entry feeds: the billing application's OLTP writes into `OW_BILLING`, plus the two
DBMS_SCHEDULER jobs (`schema/04_jobs.sql:10-31`, both DISABLED live).
Terminal outputs: issued invoices (`INVOICES`/`INVOICE_LINES`), rating results, dunning
attempts and suspensions, and the denormalized reporting estate
(`INVOICE_HEADER`/`INVOICE_LINE`, the `_HIST` twins).
Exclusions: `FIXTURE_META` (fixture bookkeeping — excluded from migration, listed in the
recon excluded-objects set so it cannot vanish silently); the CUSTBILL chain (pipeline 2);
the Python/Scala analytics (pipeline 3).

Two facts that shape everything downstream:

1. **Two table generations share one schema.** The packages operate on the modern set
   (`TENANTS`, `SUBSCRIPTIONS`, `PLANS`, `RATING_*`, `INVOICES`, `INVOICE_LINES`,
   `CREDIT_NOTES`, `DUNNING_ATTEMPTS`, `NOTIFICATIONS`, `BILLING_AUDIT_LOG` — 156 rows
   total). The volume lives in the legacy set (`CUSTOMER_MASTER` 25,000,
   `INVOICE_LINE` 150,000, `INVOICE_HEADER` 18,750, `ENTITY_ATTR_VALUE` 8,333), which no
   package reads or writes — `schema/02_horror.sql:401-404` says so outright: the bulk
   `INVOICE_LINE` estate is "distinct from the transactional INVOICE_LINES used by the
   packages". So pipeline 1 is really two half-pipelines that meet only at the tenant key.
2. **State lives in package globals.** `pkg_rating` parks nine values in package variables
   between `compute_rating` and `sp_finalize_rating` (`packages/03_pkg_rating.sql:6-17`),
   and `pkg_invoicing` re-reads `pkg_rating.g_overage_amount`
   (`packages/04_pkg_invoicing.sql:48-49`). Session-scoped mutable state is the API. Any
   conversion must make that dataflow explicit; nothing in Lakebase or Spark reproduces
   PL/SQL package state.

---

## 2. Unit inventory

Workload types: SQL (table/data), PIPELINE (streaming/batch ingest), ORCHESTRATION
(scheduler), CONSUMER (read API/report). "Risk" uses the `oracle-plsql` dialect flags.

### 2.1 Data units — Lakebase (operational, app writes)

| # | Unit | Rows | Target | Risk |
|---|---|---:|---|---|
| U-01 | `TENANTS` | 69 | `billing.tenants` | status magic numbers (10/20) |
| U-02 | `PLANS` | 3 | `billing.plans` | money `NUMBER(12,2)` → `numeric(12,2)` |
| U-03 | `SUBSCRIPTIONS` | 69 | `billing.subscriptions` | `TRG_SUB_NO_UNCANCEL` trigger rule must survive |
| U-04 | `RATING_PERIODS` | 3 | `billing.rating_periods` | deterministic MD5 id (see U-20) |
| U-05 | `RATING_RESULTS` | 3 | `billing.rating_results` | id derived from period id |
| U-06 | `INVOICES` (modern) | 3 | `billing.invoices` | name collision with `INVOICE_HEADER` (D9-01) |
| U-07 | `INVOICE_LINES` (modern) | 2 | `billing.invoice_lines` | rebuilt-from-scratch semantics |
| U-08 | `CREDIT_NOTES` | 5 | `billing.credit_notes` | burn-down order `issued_on, id` is load-bearing |
| U-09 | `DUNNING_ATTEMPTS` | 1 | `billing.dunning_attempts` | unique key implied, never declared |
| U-10 | `NOTIFICATIONS` | 1 | `billing.notifications` | `NOT EXISTS` dedupe on `(tenant, kind, sent_at)` |
| U-11 | `CODES` | 32 | `billing.codes` | read by dynamic SQL (`f_code_desc`) |
| U-12 | `CUSTOMER_MASTER` | 25,000 | `billing.customer_master` | **155 cols, 15 string dates, 10 UDF money slots, repeating groups** |
| U-13 | `ENTITY_ATTR_VALUE` | 8,333 | `billing.entity_attr_value` | EAV, everything typed as string |

### 2.2 Data units — Delta (history and reporting)

| # | Unit | Rows | Target | Risk |
|---|---|---:|---|---|
| U-14 | `CUSTOMER_MASTER_HIST` | 0 | `ow_tp.silver.customer_master_hist` | 158 cols; trigger-maintained full-row copies; empty today, so recon proves only schema |
| U-15 | `SUBSCRIPTIONS_HIST` | 0 | `ow_tp.silver.subscriptions_hist` | same, empty |
| U-16 | `INVOICE_HEADER` | 18,750 | `ow_tp.silver.invoice_header` | string dates, no FK to lines |
| U-17 | `INVOICE_LINE` | 150,000 | `ow_tp.silver.invoice_line` | largest unit; orphans expected (D8-01) |
| U-18 | `USAGE_EVENTS` | 814 | `ow_tp.silver.usage_events` | feeds rating and, later, build session B1 |
| U-19 | `BILLING_AUDIT_LOG` | 0 | `ow_tp.silver.billing_audit_log` | written by an autonomous transaction (see U-20) |

### 2.3 Code units

| # | Unit | Source | Type | Risk |
|---|---|---|---|---|
| U-20 | `pkg_ow_util` | `packages/01_pkg_util.sql` (83) | SQL/shared | **shared by all four packages (D6-01)**: `f_md5_uuid` (MD5-derived deterministic ids — every other unit's primary keys depend on it reproducing byte-for-byte), `f_code_desc` (EXECUTE IMMEDIATE for a static lookup), `f_str2dt` (returns NULL on any bad date and tells nobody), `log_msg` (PRAGMA AUTONOMOUS_TRANSACTION, commits independently, swallows its own failures) |
| U-21 | `pkg_plans` | `packages/02_pkg_plans.sql` (111) | SQL | package-state entitlement cache never invalidated; `(+)` outer joins; dynamic SQL for a static INSERT; `SELECT ... FOR UPDATE` |
| U-22 | `pkg_rating` | `packages/03_pkg_rating.sql` (223) | SQL | row-at-a-time cursor summation; date comparison via `TO_CHAR(...,'YYYYMMDD')` string compare; `LEAST/GREATEST` NULL semantics differ Oracle↔Postgres (called out in-source at :95-98); tier break hardcoded at 101; suspension proration; insert-then-catch-`DUP_VAL_ON_INDEX` upserts |
| U-23 | `pkg_invoicing` | `packages/04_pkg_invoicing.sql` (200) | SQL | tax rate hardcoded `0.0825` at :26; reads `pkg_rating` globals; `EXECUTE IMMEDIATE` delete of lines; credit burn-down decrements a running counter in a quirk the source says to preserve verbatim (:180-190); rounding applied per line and again on the total |
| U-24 | `pkg_dunning` | `packages/05_pkg_dunning.sql` (105) | SQL | **`WHEN OTHERS THEN NULL` swallows every scheduling error** (:63-66); weekend shift by `DECODE` on `TO_CHAR(...,'DY')` with English NLS; `(+)` outer join; suspension sweep writes three tables |
| U-25 | `JOB_NIGHTLY_DUNNING` | `schema/04_jobs.sql:10-19` | ORCHESTRATION | daily 02:00; currently DISABLED |
| U-26 | `JOB_PURGE_AUDIT_LOG` | `schema/04_jobs.sql:21-31` | ORCHESTRATION | 90-day retention hardcoded in the job text; also `WHEN OTHERS THEN NULL` |
| U-27 | CDC transport | new | PIPELINE | Debezium Server on EKS `otterworks-dev` → Kinesis on-demand → Lakeflow AUTO CDC into Delta. Untested matrix (D-002 fallback applies) |

Triggers (7) and sequences (5) are not separate units: each is converted with the table it
serves (`trg_customer_master_seq`/`_hist` with U-12/U-14, `trg_entity_attr_value_seq` with
U-13, `TRG_SUB_NO_UNCANCEL` with U-03). Indexes (25) are re-declared as part of their
table's unit; Delta gets none, Lakebase gets the equivalents.

---

## 3. Field/type dictionary (rules, not 400 rows)

| Legacy | Target (Lakebase) | Target (Delta) | Mark | Rule |
|---|---|---|---|---|
| `NUMBER(12,2)` / `NUMBER(14,2)` money | `numeric(12,2)` / `numeric(14,2)` | `DECIMAL(12,2)` / `DECIMAL(14,2)` | FACT | Never float. Exact-equality recon columns |
| `NUMBER(4)` status codes | `smallint` | `SMALLINT` | FACT | Magic numbers preserved; no enum rewrite in pipeline 1 |
| `VARCHAR2(36)` ids | `varchar(36)` | `STRING` | FACT | MD5-derived, must match `f_md5_uuid` exactly |
| `VARCHAR2(9)` `DD-MON-YY` dates (37 cols) | `varchar(9)` raw **plus** a generated `date` column | `STRING` raw **plus** `DATE` parsed | **INFERRED** | Keep the raw string verbatim so recon is byte-exact; add the parsed column for consumers. `f_str2dt` returns NULL on unparseable input, so parsed NULL ≠ data loss — it is the legacy behaviour and belongs in the declared anomaly set |
| `VARCHAR2(20)` `HIST_DT` | same pattern | same pattern | INFERRED | Different format from the 9-char columns; parser must not assume |
| `DATE` | `timestamp(0)` | `TIMESTAMP` | FACT | Oracle `DATE` carries a time part; truncating it would break `TRUNC(SYSDATE)` comparisons |
| `TIMESTAMP` | `timestamptz`? | `TIMESTAMP` | **INFERRED** | No zone information exists in the source. Assume UTC, declare it, and flag it — this is where invoice `issued_at` parity breaks first |
| `CHAR(1)` Y/N | `char(1)` | `STRING` | FACT | `NVL(tax_exempt_yn,'N')` semantics preserved, not converted to boolean |
| comma-separated id lists (`VARCHAR2`) | `text` verbatim | `STRING` verbatim | FACT | Not split into arrays in pipeline 1; malformed lists are declared anomalies |
| EAV `attr_value` strings | `text` | `STRING` | FACT | No type promotion |

The three INFERRED rows are the predicted recon failures, in order of likelihood:
timestamp zone, then `HIST_DT` parsing, then the 9-char date columns.

---

## 4. Dependencies (inline, as required)

| ID | Class | Contract | Status | Lead-time exposure |
|---|---|---|---|---|
| D10-01 | D10 access | Open 1521 on `sg-0eaf11f4434260e1e` to the Databricks serverless NAT range so Lakehouse Federation can read Oracle; the recon harness refuses `--family oracle` outright | **OPEN** | Blocks every unit's live recon, therefore wave 1 close |
| D10-02 | D10 access | Lakebase project `ow-tp-billing` provisioned, DSN as `OW_TP_LAKEBASE_DSN`, one branch per wave | IN PROGRESS (parent) | Blocks U-01..U-13 |
| D10-03 | D10 infra | Kinesis on-demand stream + Debezium Server on EKS | PENDING (parent) | Blocks U-27 only; fallback D-002 keeps correctness on JDBC + watermarks |
| D10-04 | D10 access | Migration identity = service principal, confirmed by owner | OPEN | Cosmetic today (doctor green), material if the PAT is reinstated |
| D6-01 | D6 shared | `pkg_ow_util` converted once in wave 0; every later unit imports it | PROPOSED | Serial floor for the whole pipeline |
| D8-01 | D8 quality | Orphans and malformed strings are reproduced, not cleaned; compared as sets | PROPOSED | Recon contract, already in `03_recon_tolerances.md` |
| D9-01 | D9 naming | Every unit mapping names which invoice pair it migrates | PROPOSED | A mis-declared mapping is a silent wrong-table migration |
| D2-01 | D2 determinism | `f_md5_uuid` must produce identical ids on the target, or every derived key diverges | **UNDECIDED** | Wave 0 must prove MD5 parity before any keyed unit runs |
| D2-02 | D2 determinism | `log_msg` is an autonomous transaction that commits even when its caller rolls back | UNDECIDED | Target has no equivalent; needs a declared rule (separate writer vs best-effort) |
| D4-02 | D4 consumer | Who reads `fn_invoice_preview`/`fn_invoice_lines`/`fn_overdue_accounts` today | UNDECIDED | Determines whether the converted read path needs an API shim at cutover |

---

## 5. Waves and fan-out batches

No two batches in the same wave write the same target. INFERRED edges are kept inside one
batch, never split.

### Wave 0 — serial (width 1), shared scaffolding

`pkg_ow_util` conversion with MD5 parity proof (D2-01), Lakebase schema + branch
bootstrap, `ow_tp.bronze/silver` conventions and landing paths, secret-scope wiring, the
canonicalization profile for the 37 string-date columns, and the CDC transport (U-27) as a
separate serial step. Nothing else may start first: every id in the estate is an
`f_md5_uuid` output.

### Wave 1 — pilot, width 3

| Batch | Units | Write targets |
|---|---|---|
| W1-A | U-01, U-02, U-11 | `billing.tenants`, `billing.plans`, `billing.codes` |
| W1-B | U-18 | `ow_tp.silver.usage_events` |
| W1-C | U-16, U-17 | `ow_tp.silver.invoice_header`, `ow_tp.silver.invoice_line` |

Deliberate mix: one Lakebase batch of tiny reference tables, one Delta batch, and one
150,000-row batch that exercises the backfill planner's chunking and the size-tiered recon
path. Harvest SKILL FEEDBACK here before widening.

### Wave 2 — width 5

| Batch | Units | Write targets |
|---|---|---|
| W2-A | U-03, U-21 | `billing.subscriptions` (+ `pkg_plans`) |
| W2-B | U-12 | `billing.customer_master` |
| W2-C | U-13 | `billing.entity_attr_value` |
| W2-D | U-14, U-15 | `silver.customer_master_hist`, `silver.subscriptions_hist` |
| W2-E | U-19, U-26 | `silver.billing_audit_log` (+ retention job) |

U-12 is alone in its batch: 155 columns and 15 of the 37 string dates make it the single
most likely unit to produce a wide diff, and a child that owns nothing else can iterate.

### Wave 3 — width 4

| Batch | Units | Write targets |
|---|---|---|
| W3-A | U-04, U-05, U-22 | `billing.rating_periods`, `billing.rating_results` |
| W3-B | U-06, U-07, U-23 | `billing.invoices`, `billing.invoice_lines` |
| W3-C | U-08 | `billing.credit_notes` |
| W3-D | U-09, U-10, U-24 | `billing.dunning_attempts`, `billing.notifications` |

W3-B depends on W3-A (invoicing calls `sp_finalize_rating` at
`packages/04_pkg_invoicing.sql:134`) and W3-C (credit burn-down writes `credit_notes`),
so W3-B's child receives both as read-only prerequisites and W3-C is serialized ahead of
it within the wave — three launches, then one. `pkg_dunning` writes `tenants` and
`subscriptions` (`packages/05_pkg_dunning.sql:81-84`), which W2-A owns; W2 must be merged
before W3-D launches. That is the wave gate, not a collision.

### Wave 4 — width 1

`JOB_NIGHTLY_DUNNING` (U-25) as a Lakeflow Job, schedule created PAUSED.

Serial floor: wave 0 (`pkg_ow_util` + MD5 parity) → the rating→invoicing→dunning chain.
Projected concurrency never exceeds 5 sessions, inside the width confirmed at intake.

---

## 6. Recon plan per unit

Contract from `03_recon_tolerances.md`: money and row counts exact, `1e-9` relative on
other floats, dates ISO-canonicalized before comparison, anomalies compared as sets, full
row-level diff below 5,000,000 rows.

| Units | Recon |
|---|---|
| U-01..U-11, U-19 (≤ 32 rows) | Full row-level diff, every column, plus aggregates. Trivially cheap |
| U-12 (25,000 × 155) | Full row-level diff. Per-column aggregates on all 38 money columns; the 15 string-date columns compared **raw** (byte-exact) and again **canonicalized**; the two must disagree only on rows in the declared unparseable set |
| U-13 (8,333) | Full row-level diff on `(entity, attr, value)`; duplicate-attribute rows compared as a set |
| U-16, U-17 (168,750) | Full row-level diff (below threshold). Orphan `INVOICE_LINE` rows compared as an exact set — reproducing them is the pass condition |
| U-14, U-15 (0 rows) | Schema-only parity plus an empty-set assertion; recorded as **not data-proven** so nobody mistakes it for evidence |
| U-18 (814) | Full diff; `units` summed per tenant/period to match `pkg_rating`'s cursor arithmetic |
| U-20..U-24 (behavioural) | Output-equivalence: run each entrypoint over every tenant on both sides and diff the result sets. `fn_usage_rating`, `fn_usage_summary`, `fn_invoice_preview`, `fn_invoice_lines`, `fn_overdue_accounts` are read-only and diff directly; `sp_finalize_rating`, `sp_issue_invoice`, `sp_schedule_dunning`, `sp_suspend_overdue` are diffed by their written rows after a controlled run on the fixture |
| U-25, U-26 | No data recon. Verified by run-history equivalence on the fixture; the Oracle jobs are DISABLED, so there is no live run to compare against — stated as a gap, not papered over |
| U-27 | Stream-vs-batch convergence check: CDC-applied Delta state must equal a JDBC snapshot taken after the stream is caught up |

Determinism rules to agree before wave 1 (they will otherwise cry wolf):
`fn_overdue_accounts` and `sp_schedule_dunning` order by `issued_at, id` so they are
deterministic; `fn_usage_summary` orders by kind; the credit burn-down depends on
`issued_on, id` order and must be applied in that order on the target;
`sp_schedule_dunning`'s swallowed errors mean a legacy run can silently schedule fewer
attempts than expected, so the comparison baseline is the rows it actually wrote.

Legacy-side query cost: every unit reads its source table once per recon run. The heaviest
wave is wave 1 at roughly 170,000 source rows, well inside the concurrency cap of 4
concurrent source queries. All live reads go through Lakehouse Federation once D10-01 is
answered; until then recon can only run DEGRADED against snapshots, which is not STOP D
evidence.

---

## 7. Risks

1. **D10-01 unanswered** — no merge-authority recon for any unit. Everything else can
   proceed; nothing can close.
2. **MD5 id parity (D2-01)** — if `f_md5_uuid` is not reproduced byte-for-byte, every
   derived primary key in rating, invoicing and dunning diverges and every downstream diff
   is red for one reason. Proven in wave 0 or the pipeline is built on sand.
3. **Timestamp zone (INFERRED)** — no zone in the source; the assumption is declared, not
   discovered.
4. **`WHEN OTHERS THEN NULL` in `pkg_dunning` and `JOB_PURGE_AUDIT_LOG`** — the legacy
   system's observable behaviour includes losing errors. The conversion must not silently
   "fix" that during pipeline 1, or recon fails for a good reason; the fix belongs in a
   follow-up with the user's agreement.
5. **Package-global state** — `pkg_invoicing` reading `pkg_rating`'s globals is an
   implicit contract that must become an explicit dataflow. The most likely source of a
   subtle wrong-number bug.
6. **Empty history tables** — `CUSTOMER_MASTER_HIST`, `SUBSCRIPTIONS_HIST` and
   `BILLING_AUDIT_LOG` hold zero rows, so their migrations cannot be data-proven here.
7. **Debezium on 26ai (D10-03)** — outside the tested matrix; correctness path falls back
   to JDBC + watermarks per D-002.
