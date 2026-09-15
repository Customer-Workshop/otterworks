# Pipeline 1 — STOP E: cutover decision packet

**Pipeline:** monthly invoicing, Oracle `OW_BILLING` → Lakebase PostgreSQL (operational) +
Databricks Delta `ow_tp` (analytical)
**Date:** 2026-09-15 · **Status:** awaiting customer decision · **Prepared by:** migration
orchestrator session
**Not self-approved.** Nothing in this packet authorizes a cutover, and no production
consumer has been repointed. Cutover needs the customer-held cutover principal and an
explicit authorization reply.

---

## 1. What is being asked

Three answers, in order of lead time:

1. **Two named owners** (§5) — the temporary shim removal owner and the out-of-database
   audit-writer owner. Both are blocking: the shim is application work and the audit writer
   is a correctness deviation that cutover would carry into production.
2. **One routing decision** (§4, consumer 2) — `reports.py` reads analytical-track tables
   directly with Oracle-specific SQL, so it fits neither of the D4-02 rules. Rebuild it on
   DBSQL, or give it a temporary shim like the package callers.
3. **Cutover authorization itself** (§10) — only after 1 and 2, and only with the residual
   risk in §6–§8 read as stated rather than as "all units passed".

---

## 2. Delivery state

28 units across 5 waves. All reconciled verdicts are **DEGRADED** and **not** official
harness verdicts (§6).

| Wave | Units | Outcome |
|---|---|---|
| 0 | 2 (`p1-pkg-ow-util`, `p1-cdc-transport`) | closed, both PASS |
| 1 | 6 (tenants, plans, codes, usage_events, invoice_header, invoice_line) | closed, 6/6 PASS — pilot |
| 2 | 9 (subscriptions, pkg_plans, customer_master, EAV, both `_hist`, audit log, purge job, credit_notes) | closed after a halt on two undeclared write targets, then 9/9 PASS |
| 3 | 7 placed + `p1-pkg-rating` attempted | **PARTIAL.** 7 PASS; `p1-pkg-rating` BLOCKED — see §3 |
| 4 | 4 (`p1-usage-events-oltp`, `p1-pkg-rating` retry, `p1-job-nightly-dunning`, `p1-pkg-invoicing`) | closed, 4/4 PASS |

Wave 3 stays PARTIAL in the record. `p1-pkg-rating` ran there, could not be delivered, and
was re-placed to wave 4 behind the new operational `usage_events` unit; wave 3's artifacts
were not rewritten to erase that.

**Empty-source caveat, carried verbatim from wave 2:**

> three units are schema-plus-empty-set assertions, their idempotency reruns prove nothing,
> and the purge job has zero runs.

The nightly dunning job (wave 4) is the same shape: it exists paused on cron `0 0 2 * * ?`
UTC matching the legacy `FREQ=DAILY;BYHOUR=2;BYMINUTE=0` entry, and has zero runs. The
legacy job is disabled at source, so there is no live behaviour to compare against — the
equivalence is a schedule-and-script match, not a behavioural one.

---

## 3. `usage_events` on both tracks — system of record and drift

D-011 added an operational copy so `pkg_rating` had a table to read. The estate has one
`usage_events`; the target has two.

| Copy | Location | Purpose | Fed by |
|---|---|---|---|
| Operational | Lakebase `billing.usage_events` | read row-at-a-time by `pkg_rating`/`pkg_invoicing` | Oracle, directly (JDBC load; CDC after cutover) |
| Analytical | Delta `ow_tp.silver.usage_events` | reporting and history | Oracle, via the CDC/bronze path |

**System of record:**

- **Before cutover:** Oracle `OW_BILLING.USAGE_EVENTS` is the system of record for both
  copies. Both are derived; neither is authoritative.
- **After operational cutover:** Lakebase `billing.usage_events` becomes the operational
  system of record — it is what the application writes and what invoicing reads.
- **Delta stays the analytical/reporting copy** and is never written by the application.
- **Neither copy is ever sourced from the other.** Both refresh from Oracle (or, after
  cutover, from the operational Lakebase table via the CDC/ingest path that replaces the
  Oracle feed). Reconciling one target against the other would be self-certification, and
  every reconciliation in this run compared each copy to Oracle independently.

**What breaks if they drift.** Invoicing computes rated usage from the operational copy;
finance reads volumes and revenue from the analytical copy. A drift means an invoice that
does not match the report that explains it, with no error raised on either side — the
symptom is a customer dispute, not an alert. Today the two agree exactly (814 rows, identical
SHA-256 row digest, empty set differences both ways, all three sources agreeing), so this is
a maintenance obligation, not a current defect.

**This needs a named owner** (§5, owner 3): who keeps the two copies in step after cutover,
by what mechanism, and who is paged when they diverge.

---

## 4. D4-02 consumer census and routing

Full census: `docs/migration/Pipeline1_D4-02_consumer_census.md`. The rule the user set —
shim the package callers, repoint direct table readers to the Postgres wire, flag anything
that fits neither — applied per consumer:

| # | Consumer | What it calls | Class | Routing |
|---|---|---|---|---|
| 1 | `services/legacy-billing/app/app.py` | `fn_invoice_preview`, `sp_issue_invoice`, `fn_overdue_accounts`, `sp_suspend_overdue` | package entrypoints | **SHIM.** Thin service over Lakebase preserving the existing call shapes. Explicitly temporary; needs a removal owner. |
| 2 | `services/legacy-billing/app/reports.py` | direct Oracle reads of `invoice_header`, `invoice_line`, `codes`, `customer_master`, with `NVL`/`TO_CHAR` | direct table reader, but of **analytical-track** tables | **FLAGGED — decision needed.** The simple "repoint to Postgres wire" rule does not apply: those tables live in Delta, not Lakebase. Either rebuild the queries on DBSQL, or give it a temporary shim like consumer 1. |
| 3 | `frontend/admin-dashboard` | HTTP report endpoints only, no database connection | indirect | No direct migration change; follows whatever consumer 2 becomes. |

No consumer has been repointed. All three still run against Oracle.

---

## 5. Owners required before cutover

| # | Owner for | Why it blocks | Named? |
|---|---|---|---|
| 1 | **Removal of the D4-02 temporary shim** | The shim preserves a PL/SQL call shape over Postgres. Without a named owner and a removal date it becomes permanent, and the estate keeps a legacy interface it was migrated to lose. | **UNNAMED — customer to provide** |
| 2 | **Out-of-database audit writer (P1-D1a)** | Oracle's `log_msg` commits audit rows in an autonomous transaction; Lakebase cannot — `dblink` is blocked on the project (probed, §7). The installed `billing.log_msg` runs inside the caller's transaction, so a rollback loses audit rows Oracle would have kept. Fixing it needs a writer outside the database. | **UNNAMED — customer to provide** |
| 3 | **Dual-copy `usage_events` synchronization (§3)** | Two derived copies with no owner drift silently, and the drift surfaces as an invoice that disagrees with the report. | **UNNAMED — customer to provide** |

---

## 6. How degraded the reconciliation actually is

**D10-01 was denied.** The security group was not opened, so there is no Lakehouse
Federation read path. On the user's explicit direction, pipeline 1 reconciled over JDBC from
the Devin CIDRs, with the consequence accepted in writing. Every unit therefore carries:

```
recon_grade      = DEGRADED
official_verdict = false
reason           = d10_01_denied
merge_eligible   = false
```

The comparison math is still the official harness's — every tier, canonicalization rule and
tolerance came from `recon.engine`, driven as a library. Only the *source connector* is
outside the tested matrix. Nothing here is an official Oracle harness verdict, and no PR
body, recon artifact or wave brief says otherwise.

**Named limitation — what the JDBC route does not check.** It compares **row data only**. It
does not compare constraints, indexes, triggers, grants, or any other non-row metadata.

The clearest illustration is real and from this run: **four Oracle foreign keys were missing
in Lakebase and every affected unit still passed tier 3**, because tier 3 compares rows, not
constraints. The wave-3 independent verifier found them by inspection, not by the gate. Two
more (`FK_SUB_PLAN`, `FK_SUB_TENANT` on `billing.subscriptions`) are still missing today
(§7) and are likewise invisible to the gate.

Also unverified on this route:

- **Source metadata tiers 5–7** — not run at all.
- The factory doctor's **source-principal-read-only privilege query** — the read-only Oracle
  user cannot run it.
- **`ALL_TRIGGERS` is empty** to the read-only user, so source trigger existence could not be
  confirmed from the live database; it is repo-source evidence only.
- **Autonomous audit commit independence** — unverifiable without a write.
- **Live execution of the writing routines** (`sp_issue_invoice`, `sp_finalize_rating`,
  `fn_invoice_preview`) — the read-only Oracle user has no `EXECUTE`, and running them on the
  target would have written rows no source run produced.
- **`billing.rating_state`** has no direct Oracle counterpart to reconcile against; it is
  package-internal state.

What *is* exact: money is compared exactly, row counts exactly, other floats at 1e-9
relative, dates ISO-canonicalized, declared anomaly sets compared as sets, idempotency proven
by rerun where a rerun was safe, and every result recomputed from the target platform rather
than from the CDC output the unit itself produced.

---

## 7. Open defects and divergences carried into cutover

1. **Audit logging is not autonomous (P1-D1a) — deviation, not just divergence.** Wave 0's
   P1-D1 required `log_msg` to be a best-effort writer not enrolled in the caller's
   transaction. `dblink` is blocked on the Lakebase project (probed directly), so the
   installed `billing.log_msg` is plain in-transaction PL/pgSQL. A caller that rolls back
   loses audit rows Oracle would have committed. Needs owner 2.
2. **`log_msg` is transitive across every package.** The legacy util package writes the
   audit log from inside every other package, so any unit that converts a package inherits a
   write to `billing.billing_audit_log` that its own batch does not declare. It halted wave 2
   (`w2-a`) and wave 3 twice, and one batch initially converted `pkg_dunning` *without* its
   logging to stay in scope — the wrong resolution. Handled by declaring the runtime write on
   every package batch and restoring the dropped `log_msg` calls (D-009), not by removing
   behaviour. A future manifest that does not model it will reproduce the same halt.
3. **Two Oracle foreign keys still missing:** `FK_SUB_PLAN` and `FK_SUB_TENANT` on
   `billing.subscriptions`. Invisible to row parity (§6). The owning unit is in an
   already-merged earlier wave, so wave 4 reported rather than patched it.
4. **`TRG_USAGE_EVENTS_CHECK` has no Postgres equivalent** on `billing.usage_events`
   (units > 0, known kind). `billing.usage_events` is the operational front door that will
   take application writes after cutover, so the validation rule is simply absent there today.
5. **No converted routine has ever run and committed.** Every execution was a fixture or a
   rolled-back transaction, so `billing.billing_audit_log` and `billing.rating_state` both
   hold **zero rows**. The audit-write path and the rating→invoicing hand-off are installed,
   not exercised. One authorized committed live run before cutover would close this.
6. **Mapping specs were corrected after the freeze.** Six columns typed as Postgres
   `timestamptz` were re-typed to zoneless `timestamp`, plus `billing.rating_state.updated_at`
   separately (D-010). Oracle `TIMESTAMP` carries no zone, so `timestamptz` was a spec defect:
   it reads back as a different value and fails tier 3 on every row. Recorded as a mapping
   correction under parent authority — **tolerances were not changed**, money stays exact,
   canonicalization untouched. The generator now emits `timestamp(p)` so it cannot regenerate.

---

## 8. Incomplete, blocked and unproven work

- Wave 3 is **PARTIAL**; `p1-pkg-rating` was BLOCKED there and delivered in wave 4.
- Three wave-2 units are empty-set assertions and the purge job has zero runs (§2, verbatim).
- The nightly dunning job has zero runs and its legacy counterpart is disabled.
- Package behavioural parity for the writing routines rests on source reading plus fixture
  and rolled-back runs, not on a committed live execution (§7.5).
- Tiers 5–7 and the non-row metadata classes were never checked (§6).

---

## 9. What has *not* been touched

- **No production cutover has occurred.** No consumer has been repointed; `app.py`,
  `reports.py` and the dashboard all still run against Oracle.
- No write to the Lakebase `production` branch; all work is on `mig-p1-w2`.
- Oracle is unchanged apart from the one pre-authorized supplemental-logging change; no
  schema, data or job changes, and no further Oracle writes.
- No cutover principal was requested or held.

---

## 10. Authorization

Cutover requires, in one reply: the three owner names (§5), the `reports.py` routing decision
(§4), and an explicit authorization to repoint, executed with the customer-held cutover
principal. Until then pipeline 1 stops here.

Recommended sequencing once authorized:

1. **Finish the schema on `mig-p1-w2`:** add `FK_SUB_PLAN` and `FK_SUB_TENANT` to
   `billing.subscriptions`, and an equivalent of `TRG_USAGE_EVENTS_CHECK` on
   `billing.usage_events`.
2. **Build the out-of-database audit path** (owner 2) and deploy it before validating.
   `billing.log_msg` cannot call out: Postgres has no autonomous transaction and a second
   connection needs `dblink` or `postgres_fdw`, both refused by this Lakebase project, so
   there is no in-database wiring that makes the function rollback-surviving. The writer has
   to sit **above** the database — the D4-02 shim service holding a second connection, or an
   async sink the shim publishes to — and every caller path that must keep its audit trail
   has to go through it. That includes the nightly dunning job, which does not call through
   the shim today; scoping that path is part of owner 2's work. The in-database
   `billing.log_msg` insert stays as the in-transaction best effort it is.
3. **Promote the database.** Everything delivered lives on Lakebase branch `mig-p1-w2`;
   `production` has none of it. Promote `mig-p1-w2` → the production branch of project
   `ow-tp-billing` (Lakebase branch promotion, with the pre-promotion production branch
   retained as the rollback point), then verify on the **production endpoint** that every
   object exists: the `billing` tables with their row counts, the constraints, and the
   routines `sp_issue_invoice`, `fn_invoice_preview`, `fn_invoice_lines`,
   `sp_finalize_rating`, `fn_usage_rating`, `fn_usage_summary`, `sp_schedule_dunning`,
   `sp_suspend_overdue`, `fn_overdue_accounts`, `sp_assign_plan`, `fn_plan_entitlements`,
   `log_msg`. **This step is not authorized by this packet and no session has ever written
   the production branch;** it is the customer's to execute with the cutover principal.
4. **One committed live run** of the converted routines on the promoted database, driven
   **through the shim and its audit path**, covering both the success path and a **caller
   rollback**, to prove the audit row survives the rollback and the rating→invoicing hand-off
   writes `billing.rating_state`. Roll back to the retained branch if it fails.
5. Repoint consumer 1 → resolve consumer 2 per the decision above.
6. Retire the shim on owner 1's date — **only after** its audit path has moved to a
   standalone sink or the replacement caller layer, with the rollback validation from step 4
   re-run against that permanent path. Rollback-surviving audit logging outlives the shim;
   `billing.log_msg` stays transaction-bound, so retiring the shim while it is the only
   out-of-database writer puts the divergence straight back.

The order matters in two places. Repointing a consumer before the promotion sends production
traffic to a database where `billing.sp_issue_invoice` does not exist. And validating before
the audit path is deployed can only exercise the in-transaction `log_msg` that is being
replaced, which is the behaviour already known to fail.
