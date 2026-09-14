# STOP C — P1 Monthly invoicing: approve the migration plan

Date 2026-09-14. Blocks per `stop_mode: soft` (60 s default-accept), except that nothing in this packet touches production.

## Decision

Approve the P1 plan: 5 units in 3 single-batch waves, Lakebase branch per batch, like-for-like PL/pgSQL ports plus three
new intended-model surfaces, recon FULL with `AS OF SCN` pins, and the dependency decisions in the table below.

Artifacts: `docs/migration/P1_monthly_invoicing_analysis.md` (units, dictionary, recon plan, risks, DAG),
`docs/migration/P1_monthly_invoicing_plan.md` (decisions, schedule, gate, governance), `.migration/waves/wave-{0,1,2}.json`
(complete child briefs), `.migration/04_dependency_register.md` (D4-6, D7-2, D9-2, D9-3, D10-9..11 added),
`.migration/09_capabilities.json` (plan-time doctor).

## Units and waves

| Wave | Batch / branch | Units | Size |
|---|---|---|---|
| 0 | `mig-p1-w0-b1` | U0 shared-core: `CODES`, `PLANS`, `TENANTS`, `BILLING_AUDIT_LOG`, `PKG_OW_UTIL`, audit sequence/trigger + scaffolding (recon Oracle adapter, Delta reference copies) | M |
| 1 | `mig-p1-w1-b1` | U1 plans-subscriptions (`SUBSCRIPTIONS`, `SUBSCRIPTIONS_HIST`, `PKG_PLANS`, 2 triggers); U2 usage-events (`USAGE_EVENTS`, check trigger, ingest surface) | M, S |
| 2 | `mig-p1-w2-b1` | U3 rating (`RATING_PERIODS`, `RATING_RESULTS`, `PKG_RATING`); U4 invoicing-credits (`INVOICES`, `INVOICE_LINES`, `CREDIT_NOTES`, `PKG_INVOICING`; XL -> contract PR then implementation PR) | L, XL |

Width 1 per wave (D10-11: the fan-out workflow refuses to launch while the doctor is `ready=false` on the accepted human-PAT
row, so no wave may hold two batches). 7 PRs total. Serial floor 3 child sessions + 3 verifier passes; lead times (CDC
containers D10-10, Lakehouse Sync UI enablement D10-9) gate the recon posture, not conversion.

## Dependency decisions requiring approval

| ID | Proposed |
|---|---|
| D2-1 / D2-2 | Wave 0 owns the shared tables in Lakebase; Delta copies via Lakehouse Sync when enabled, freeze-and-load until then. `CUSTOMER_MASTER` moves to P3. |
| D4-6 | New `invoicing.close_billing_period(period_start, period_end)` as the scheduler entry point (Oracle has none). |
| D5-1 | `JOB_PURGE_AUDIT_LOG` ported as an unscheduled procedure; scheduling is a STOP E item. |
| D6-1 / D6-2 | U0/U1 own `TENANTS`/`SUBSCRIPTIONS` and their triggers; P2 adds its writers later without DDL. |
| **D7-2** | Oracle P1 emits **no** notification at invoice issue. Option B (recommended): keep `sp_issue_invoice` like-for-like; P2 emits invoice notifications. Option A: emit `NOTIFICATIONS(kind_cd=1)` inside U4 (new behaviour, excluded from source recon). |
| D9-1 | Sequences `CACHE 1`, `setval` after load, never compared. |
| D9-2 | Package globals replaced by composite return types; `g_last_*` caches dropped (no reader found). |
| D9-3 | Autonomous audit logger becomes in-transaction; rollback-loss accepted, compared on content. |
| D10-5 | Thin read-only `python-oracledb` adapter for `dbx-recon` built in wave 0. |
| D10-9 | **Request fired**: enable Lakehouse Sync (UI-only) on the wave-close branch schema `ow_billing` -> `ow_tp.silver`. Owner: parent/customer. |
| D10-10 | **Request fired**: deploy Debezium/Kafka/Connect containers on the Oracle host per DEC-A; until live, Tier 6 recorded `skipped/no_cdc`. |
| D10-11 | Accept single-batch waves as the consequence of the accepted PAT identity. |

## Standing preconditions carried to STOP E (unchanged)

Cutover stays blocked until the customer names the billing service and the usage-event producers and the path
usage event -> rating -> invoice -> notification is demonstrated end to end (DEC-B1). The three new surfaces
(`ingest_usage_event`, `close_billing_period`, `issue_credit_note`) are the interfaces those services would call; no caller
is invented and none is wired here.

## Gate

Per unit: fixture-first, one live `dbx-recon --mode transactional --target-kind lakebase --depth full` at an `AS OF SCN`
pin, tiers 1-5,7 PASS with 0 unexplained diffs, Tier 4 dual-run parity per routine, `result.json` on the PR, independent
verifier PASS before merge (`verify_depth` full on waves 1-2).

## Recommendation

Approve as written, with D7-2 option B.

## Exact reply

`Approve STOP C: P1 plan as written, D7-2 option B.`

To choose the other notification option instead: `Approve STOP C: P1 plan as written, D7-2 option A.`
