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

## 3. Query history / consumer evidence — partially unblocked (evidence gap remains)

Consumer detection for this family normally mines query history. Probed four surfaces as
the schema owner; initially all four were unavailable, and three have since been granted:

| Surface | As `OW_BILLING` (at intake) | As `SYSDBA` | As `OW_BILLING` (after grant) |
|---|---|---|---|
| `v$sql` (shared SQL area) | `ORA-00942` | 481 rows | 524 rows |
| `dba_hist_sqlstat` (AWR) | `ORA-00942` | 0 rows | `ORA-00942` (not granted; 0 rows to see) |
| `v$active_session_history` (ASH) | `ORA-00942` | 8 rows | 18 rows |
| `unified_audit_trail` | `ORA-00942` | 13,893 rows | 13,894 rows |

Read this carefully, because the two failure causes have different fixes:

- `v$sql` / ASH / audit trail were a **grant problem**: the data existed, the migration
  identity could not see it. **Resolved** — see D10-1 in §6 for the exact grants applied
  and the verification above.
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
- `unified_audit_trail`, now readable: usable as a *sampled* consumer signal over the
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

## 6. Customer decisions and dependencies

Decisions taken by the customer at intake (2026-08-28):

| ID | Item | Answer |
|---|---|---|
| ~~OPEN-1~~ | Estate scope | **`OW_BILLING` only.** `COMMISSION_DW` (star schema + PL/SQL ETL + MV under `services/industry-solutions/insurance/db/olap/`) is **out of scope** for this run — not deferred into a wave of it, simply not in this run's inventory. |
| ~~OPEN-2~~ | JDBC path Databricks → Oracle for Lakehouse Federation | **Approved.** Recon mode LIVE; federation-first coexistence stands (§5). |
| TOL-1 | Money comparison tolerance | **Exact to the cent.** Any difference on a `NUMBER(14,2)` amount fails recon — no epsilon, no relative tolerance on totals. Sets the target type to `DECIMAL(14,2)` and forbids any double-precision path through rating or invoicing. |
| TOL-2 | Unparseable `VARCHAR2(9)` date values | **Quarantine the row, continue the load, count quarantined rows in recon.** Quarantine counts are recon output, not a warning to be swallowed; a load that quarantines everything must fail loudly rather than report success on zero rows. |
| PILOT-1 | Pilot composition | **`PKG_RATING` + `PKG_INVOICING` only — 2 units**, well under the width cap. Deliberately the hardest units first: they are the critical path and the slowest-converting, so the pilot's feedback is worth the most before fan-out. |
| D4-1 | Consumer population | **Declared UNMAPPED by the customer.** Nothing is known to read `OW_BILLING` beyond the batch chain and the finance report, and nothing rules others out either. |
| D10-1 | Catalog/workload access for the migration identity | **Targeted grants, not `SELECT_CATALOG_ROLE`** — least privilege deliberately chosen over breadth. Applied and verified (below). |

TOL-1 and TOL-2 interact, and the chain must not lose the interaction: money is compared
exactly, but rows can be quarantined for an unrelated bad date. A quarantined row removes
its amounts from the target totals, so **recon must compare money over the same row
population on both sides** (source minus quarantined, versus target) or every quarantine
will present as a money mismatch. State the quarantine count alongside every money
comparison.

**D4-1 is a declared coverage gap, not a task.** With no query history (§3) and the
consumer population declared unmapped, no sweep in this run can prove who reads the
estate. Per the contract policy, that must be written into the contract as an explicit
coverage gap up front and surfaced at cutover authorization — not discovered at rollup,
and never quietly converted into "no consumers found". Concretely, this means cutover
carries an unquantified risk of breaking an unknown reader, and the D10-1 grant (now
applied) plus an observation window on `unified_audit_trail` is the only thing that would
narrow it.

### D10-1, closed

Granted in `FREEPDB1`, exactly three objects and nothing else:

```sql
GRANT SELECT ON SYS.V_$SQL                     TO OW_BILLING;
GRANT SELECT ON SYS.V_$ACTIVE_SESSION_HISTORY  TO OW_BILLING;
GRANT SELECT ON AUDSYS.UNIFIED_AUDIT_TRAIL     TO OW_BILLING;  -- not SYS; PUBLIC synonym only
```

Two notes for anyone reproducing this: the grantable objects are the `V_$` base views, not
the `V$` synonyms, and `UNIFIED_AUDIT_TRAIL` is owned by `AUDSYS` — granting it on `SYS`
fails with `ORA-00942`, which is easy to misread as the same permission error the grant was
meant to fix. Re-probed as `OW_BILLING` afterwards to confirm the grants took (§3).

AWR was deliberately left out of the grant: it holds 0 rows even for SYSDBA, so access to
it would buy nothing.

**What this does and does not fix.** The migration identity can now read the audit trail
and the live shared-pool/ASH snapshots, which makes the sampled consumer signal in §3 real
rather than aspirational. It does **not** produce historical workload coverage — `v$sql` is
a volatile shared-pool snapshot and the audit trail records what auditing was configured to
record. D4-1 therefore stands as a coverage gap regardless of this grant, and the honest
mitigation is an audit-trail observation window long enough to catch periodic readers
(month-end especially) before cutover authorization.

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
- Family defaults and complexity weighting (§5).
- Tolerances: money exact to the cent, unparseable dates quarantined and counted (§6).
- Pilot: `PKG_RATING` + `PKG_INVOICING`, 2 units (§6).
- D4 consumer population declared unmapped — carry as a contract coverage gap (§6).
- D10-1 catalog access: granted, verified, and closed — do not re-request it (§6).
- Baseline volumes for recon reference (§7).

Still to be decided downstream, by the party named:

- **Audit-trail observation window** (STOP A): how long to sample `unified_audit_trail`
  before cutover authorization, now that it is readable. The only lever left on D4-1.
- **Pipeline choice** (STOP B) and **fan-out width for the waves after the pilot**
  (STOP C): user's call, unchanged by this intake.

No inventory, analysis, or conversion was performed in this session, per the front-door
scope.
