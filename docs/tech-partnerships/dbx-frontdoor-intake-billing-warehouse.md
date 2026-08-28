# DBX front-door intake — OtterWorks billing warehouse estate (Oracle)

Front-door intake record for the Databricks migration chain. Everything below is either a
FACT with a cite (a live probe or a file in this repo) or an OPEN item owned by the
customer. Downstream playbooks (`!dbx_migration_setup` → `!dbx_estate_inventory` → …)
consume this file and must not re-ask anything marked FACT.

Probe date: 2026-08-28. Probe script: `dbx_intake_probe.sql` (15 read-only probes, run as
`OW_BILLING` and again as `SYSDBA`). Raw output is attached to the intake session.

## 1. Engine and version — PINNED

| Field | Value | Evidence |
|---|---|---|
| Engine | Oracle Database (single-instance, PDB `FREEPDB1`) | probe P1 |
| Edition/banner | `Oracle AI Database 26ai Free Release 23.26.3.0.0` | probe P1/P2 |
| Version | `23.0.0.0.0` (full `23.26.3.0.0`) | probe P1 |
| Warehouse schema | `OW_BILLING` — **in scope for this run** (customer decision) | probe P3 |
| Connection | host port 52521 → container 1521, service `FREEPDB1` | `docker-compose.oracle-billing.yml` |
| Family | Oracle EDW — SQL warehouse estate | this playbook |

Note for the dictionary: this is the **Free** distribution. AWR/ASH-dependent tooling and
Diagnostics-Pack views are not available to lean on for workload evidence (see §3), and
resource limits (2 CPU threads, 2 GB SGA, 12 GB user data) cap any timing measurement
taken here — do not use this instance to size target compute.

## 2. Catalog access — WORKS

One live metadata query (`user_objects` census) succeeded as the schema owner:

| Object type | Count |
|---|---|
| TABLE | 20 |
| PACKAGE / PACKAGE BODY | 5 / 5 |
| TRIGGER | 7 |
| JOB (DBMS_SCHEDULER) | 2 |
| SEQUENCE | 5 |
| INDEX | 25 |
| **VIEW** | **0** |

Also confirmed reachable as `OW_BILLING`: `user_tab_columns`, `user_dependencies` (74
dependency edges: 31 → PACKAGE, 30 → TABLE, 8 → SYNONYM, 5 → SEQUENCE), `user_source`,
`user_scheduler_jobs`, `all_objects` (visibility beyond own schema), `v$version`.

Two consequences the chain must carry:

- **There is no view layer.** The warehouse's presentation logic is not in views; it is in
  PL/SQL package bodies plus the batch chain. The usual "convert N views first" wave does
  not exist here, and the unit mix shifts to the slowest-converting category up front.
- **The dependency graph is procedural, not relational.** `user_dependencies` gives
  package→table edges, so lineage extraction works, but it says nothing about who *reads*
  the outputs. That is the D4 problem in §3.

## 3. Query history / consumer evidence — BLOCKED (D10, evidence gap)

Consumer detection for this family normally mines query history. Probed four surfaces as
the schema owner; all four are unavailable:

| Surface | As `OW_BILLING` | As `SYSDBA` |
|---|---|---|
| `v$sql` (shared SQL area) | `ORA-00942` | 481 rows |
| `dba_hist_sqlstat` (AWR) | `ORA-00942` | 0 rows |
| `v$active_session_history` (ASH) | `ORA-00942` | 8 rows |
| `unified_audit_trail` | `ORA-00942` | 13,893 rows |

Read this carefully, because the two failure causes have different fixes:

- `v$sql` / ASH / audit trail are a **grant problem**: the data exists, the migration
  identity cannot see it. Fixable with `SELECT_CATALOG_ROLE` (or targeted `SELECT` grants)
  — registered as **D10-1** below.
- AWR returns **0 rows even as SYSDBA**: on this distribution there is no retained
  historical workload repository to mine at all. A grant will not conjure it. Even with
  D10-1 granted, `v$sql` is a volatile shared-pool snapshot (481 rows, aged out
  continuously) and the audit trail records *sessions and statements as configured*, not a
  complete historical query census.

**Therefore the D4 consumer sweep runs without its best evidence source, permanently.** It
must be driven from the artifacts instead, all of which are in this repo and all of which
are weaker (they show what was *written*, not what currently *runs*):

- `etl/legacy-extra/crontab` — the schedule, and the closest thing to an architecture
  diagram the estate has.
- `etl/legacy-extra/jobs/*` (ksh/bash/Perl) and `etl/legacy-extra/run_all.sh` — the load
  and report chain.
- `services/legacy-billing/db/oracle/schema/04_jobs.sql` — in-database scheduled work.
- Application call sites into `OW_BILLING` (`services/`), plus the report distribution
  list baked into `finance_excel_report.pl`.
- `unified_audit_trail` once D10-1 lands: usable as a *sampled* consumer signal over the
  observation window, not as a historical census. Worth taking; not worth trusting alone.

Any inventory claim of the form "nothing reads this" must be labelled as
artifact-derived, not history-derived, for the whole engagement.

## 4. Dialect skill — NONE EXISTS (wave-0 item)

There is no Oracle/PL/SQL → Databricks dialect skill in this repo or in the sibling
migration repos (checked `.agents/skills/` across them; the nearest neighbours are
`sas-to-databricks-conversion` and `testing-recon-suite`, neither of which covers this
dialect). Stating that plainly rather than pretending coverage:

- **Interim policy:** generic ANSI SQL translation, with every Oracle-specific semantic
  decided in the dictionary before fan-out, not per child.
- **Wave-0 item:** build `oracle-plsql-to-databricks` as a repo skill, seeded from the
  pilot wave's findings, and harvest into it between every wave.

Hazards already visible from the probe, which the dictionary must resolve first (each one
is a silent-wrong-answer class, not an error class):

| Hazard | Evidence | Why it bites |
|---|---|---|
| Dates stored as strings | `CUSTOMER_MASTER.SIGNUP_DT`, `LAST_ACTIVITY_DT`, `LAST_INVOICE_DT`, `LAST_PAYMENT_DT`, `TERMINATE_DT` are all `VARCHAR2(9)` (probe P15) | parse rule, century window, and unparseable-value policy must be one decision, not 20 |
| Money as `NUMBER(14,2)`, codes as `NUMBER(4,0)` | probe P15 | Delta `DECIMAL(14,2)` vs double; rounding/truncation on aggregates is the classic first recon failure |
| Oracle `NUMBER` with no precision | `01_tables.sql` | needs an explicit target-type rule |
| 155/158-column tables | `CUSTOMER_MASTER` 155, `CUSTOMER_MASTER_HIST` 158 (probe P4) | column-level mapping is the bulk of the dictionary work |
| EAV attributes | `ENTITY_ATTR_VALUE`, 8,333 rows | typed-column pivot decisions belong in the plan, not in a child |
| `WHEN OTHERS THEN NULL` | `04_jobs.sql`, package bodies | legacy swallows failures; target must not silently reproduce that, and recon must not credit it |
| Trigger-resident logic | 7 triggers, incl. history capture (`TRG_CUSTOMER_MASTER_HIST`, `TRG_SUBSCRIPTIONS_HIST`) and a guard (`TRG_SUB_NO_UNCANCEL`) | business rules with no call site; easy to miss entirely |

## 5. Warehouse-family defaults for the chain

Set here so downstream sessions inherit them:

- **Unit** = one PL/SQL package (or a coherent procedure group within one), one
  DBMS_SCHEDULER job, one trigger-resident rule, or one load/report script. Views: N/A.
- **Complexity ranking weights procedures heavily** — this family's schedule risk. Source
  volume, from `user_source` (probe P6): `PKG_RATING` 190 lines, `PKG_INVOICING` 173,
  `PKG_PLANS` 90, `PKG_DUNNING` 87, `PKG_OW_UTIL` 60. Rating and invoicing are the
  critical path and should carry the pilot, not the tail.
- **Lineage extraction** = catalog metadata + `user_dependencies` edges + the batch
  chain and crontab. Query history is **not** an input here (§3).
- **Dominant surface** = SQL/PL-SQL (procedural), with an ORCHESTRATION surface for the
  scheduler jobs and crontab, and a CONSUMER surface for the finance report outputs.
- **Physical design translation** is a named dictionary concern: Oracle indexes,
  sequences, materialized-view refresh, and the history-table pattern → liquid
  clustering, identity/surrogate-key policy, and Delta table layout. Do not carry the
  index list over one-for-one.
- **Coexistence: federation-first** — Lakehouse Federation over JDBC to Oracle, **approved
  by the customer**. Recon mode is therefore **LIVE**: recon recomputes from the target and
  compares against the source over federation, and the snapshot fallback is not needed.

Target-side capability is already proven and does not need re-probing at setup: the nightly
capability preflight reported `databricks 11/0 denied` (11 probes verified, none denied) in
`#ow-migrations`/`#ow-tp-status` on 2026-08-28. Shared Databricks namespace is `ow_tp`;
use the existing serverless SQL warehouse and do not touch unprefixed objects.

## 6. Customer decisions and remaining dependency

Both intake blockers are **resolved** (customer, 2026-08-28):

| ID | Item | Answer |
|---|---|---|
| ~~OPEN-1~~ | Estate scope | **`OW_BILLING` only.** `COMMISSION_DW` (star schema + PL/SQL ETL + MV under `services/industry-solutions/insurance/db/olap/`) is **out of scope** for this run — not deferred into a wave of it, simply not in this run's inventory. |
| ~~OPEN-2~~ | JDBC path Databricks → Oracle for Lakehouse Federation | **Approved.** Recon mode LIVE; federation-first coexistence stands (§5). |

Still open, and the one thing the chain must carry forward:

| ID | Item | Impact if unresolved |
|---|---|---|
| D10-1 | Catalog/workload grant for the migration identity (`SELECT_CATALOG_ROLE`, or targeted `SELECT` on `V$SQL`, `V$ACTIVE_SESSION_HISTORY`, `UNIFIED_AUDIT_TRAIL`) | D4 consumer sweep runs on artifact evidence only; see §3. Note this is a *partial* mitigation even when granted — AWR has no rows to grant access to. |

`OW_BILLING` holds only `CREATE SESSION/TABLE/VIEW/PROCEDURE/TRIGGER/SEQUENCE/TYPE/JOB`
(probe P13) — no catalog role, which is exactly the D10-1 gap.

## 7. Baseline volumes (NS=demo, seed 714559852)

Recorded so recon has a starting reference: `CUSTOMER_MASTER` 25,000, `INVOICE_HEADER`
18,750, `INVOICE_LINE` 150,000, `ENTITY_ATTR_VALUE` 8,333, `USAGE_EVENTS` 814,
`RATING_RESULTS` 3, `INVOICES` 3, `INVOICE_LINES` 2, tenants in namespace 60. Matches the
documented baseline for this namespace.

## 8. Hand-off

Next: `!dbx_migration_setup` (target state + `.migration/` workspace + tolerances +
access checklist → STOP A), then the standard chain under `!dbx_migrate_pipeline`.

Settled here — do **not** re-ask any of it at STOP A:

- Engine and version, connection, schema (§1).
- Scope: `OW_BILLING` only (§6).
- Federation approved, recon mode LIVE (§5, §6).
- Source catalog access confirmed; target capability proven by preflight (§2, §5).
- No view layer; unit mix is procedural (§2, §5).
- No dialect skill; generic ANSI plus a wave-0 build item (§4).
- Family defaults, complexity weighting, and the pilot candidates (§5).
- Baseline volumes for recon reference (§7).

Still to be decided downstream, by the party named:

- **D10-1** (customer): the catalog/workload grant. Setup should put it on the access
  checklist; it is not a blocker for ingest, only a quality ceiling on D4.
- **Tolerances** (STOP A): must be set knowing money is `NUMBER(14,2)` and dates are
  strings — exact-match on money, and an explicit unparseable-date policy.
- **Pipeline choice** (STOP B) and **plan/fan-out width** (STOP C): user's call, unchanged
  by this intake. Pilot width ≤ 5, and rating/invoicing should be in the pilot (§5).

No inventory, analysis, or conversion was performed in this session, per the front-door
scope.
