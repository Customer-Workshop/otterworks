# P1 Monthly invoicing — migration plan (for STOP C)

Analysis: `P1_monthly_invoicing_analysis.md` (units U0-U4, dictionary, recon plan, risks). This plan turns it into an
executable schedule. Every dependency below carries a PROPOSED decision; STOP C approval makes them DECIDED. Nothing here
launches children or writes conversion code.

## 1. Inputs check

| Input | State |
|---|---|
| Analysis | current (this commit) |
| Target profiles | CORE, LAKEBASE, SQL/Delta, DATA/DEPENDENCY in `ow_billing_target_state.md` — all unit workload types covered (OLTP SQL, analytical copies) |
| Tolerances | `.migration/03_recon_tolerances.{md,json}` v `tol-p1-v1`, committed; `AS OF SCN` pins (DEC-B2) |
| factory-doctor | re-run at plan time -> `.migration/09_capabilities.json`; re-run 2026-09-14: 13 ok / 0 fail / 2 warn / 2 skipped, `ready=false` only on `databricks_identity=warn` (D10-4, accepted). `hook_platform_loaded` is now `ok` (the guard blocked the live probe), so D10-7 is observed closed at plan time and re-checked before every wave. Consequence of `ready=false` in §4 |

## 2. Dependency decisions (decide mode)

| ID | Proposed decision | Lead-time request |
|---|---|---|
| D2-1 | Wave 0 (U0) migrates `CODES`, `PLANS`, `TENANTS`, `BILLING_AUDIT_LOG`, `PKG_OW_UTIL` once into Lakebase schema `ow_billing`; P2/P3 inherit. `CUSTOMER_MASTER` moves out of wave 0 to P3 (no P1 reader). | none |
| D2-2 | Lakebase is master for `CODES/PLANS/TENANTS`; Delta copies in `ow_tp.silver` for the P3 report come from Lakehouse Sync once enabled (D10-9), freeze-and-load until then. | D10-9 request fired at STOP C |
| D3-1 | Contract: `usage.ingest_usage_event(id, tenant_id, occurred_at, units, kind_cd)`, dedupe on `id`, rejects mapped to ERRCODEs. Producers remain unnamed; STOP E precondition. | customer names producers (STOP E) |
| D4-5 | Billing service is the caller of `plans.*`, `rating.*`, `invoicing.*` over Postgres wire protocol with a customer-held role. Unnamed; STOP E hard precondition (DEC-B1). | customer names the service (STOP E) |
| D4-6 | Add `invoicing.close_billing_period(period_start, period_end)` as the scheduler entry point (new surface, PROPOSED). Tested fixture-only. | none |
| D5-1 | P1 has no scheduler job; `JOB_PURGE_AUDIT_LOG` (shared, disabled) is ported in U0 as a PL/pgSQL procedure `util.purge_audit_log()` with **no** schedule attached; scheduling is a STOP E item (pg_cron vs Lakeflow Job `ow_tp_purge_audit_log` PAUSED). | none |
| D6-1 / D6-2 | U0 owns `TENANTS`, U1 owns `SUBSCRIPTIONS` + both triggers; P2 adds `PKG_DUNNING`'s writer procedures later without DDL on these tables. | none |
| D7-2 | **Option B**: `sp_issue_invoice` stays like-for-like (no notification); invoice notification is emitted by P2 dunning/notification unit. Keeps U4 fully recon-comparable. Option A (emit in U4) available if the customer wants the demo path inside P1. | none |
| D9-1 | Sequences `seq_billing_audit_log`, `seq_subscriptions_hist`: `CACHE 1`, `setval(max+1)` after load; values never compared. | none |
| D9-2 | Package globals replaced by composite return types `rating.rating_result_t`, `invoicing.preview_t`; `g_last_*` caches dropped. | none |
| D9-3 | `util.log_msg` in-transaction; `BILLING_AUDIT_LOG` compared on `(module, message)` multiset with rollback-loss accepted (tolerance row 14). | none |
| D10-5 | Wave-0 scaffolding: thin `python-oracledb` source adapter for `dbx-recon` (read-only, `AS OF SCN`), 2-statement cap enforced by the harness. | none |
| D10-9 | Lakehouse Sync (Lakebase -> Delta) is UI-only. Request the parent/customer enable it on the wave-close branch schema `ow_billing`; until then analytical copies are freeze-and-load. | **fired at STOP C** (owner: parent, workspace UI) |
| D10-10 | Debezium + Kafka + Connect containers on the Oracle host (DEC-A) are wave-0 scaffolding built by the parent session (SSM), not by children; until live, U1-U4 rehearse with SCN-pinned freeze-and-load and transactional recon runs with `cdc_lag_max_s` unused (`isolation: as_of_scn`). | fired at STOP C (owner: this session / parent) |

## 3. Scaffolding delta (wave 0, beyond U0)

- Lakebase branch `mig-p1-w0-b1` from `production` (TTL 7d), schema `ow_billing` with sub-schemas `util`, `plans`, `usage`, `rating`, `invoicing`; roles `ow_billing_app` (owner) and `ow_billing_ro` (reader) — nothing to port from Oracle grants (`08_governance_inventory.md`: 0 object grants).
- `dbx-recon` Oracle source adapter (D10-5) + mapping template with `watermark`/`identity` per table (analysis §6).
- Delta: `ow_tp.silver.{codes,plans,tenants}` + `ow_tp.ops.p1_recon_runs` (ns=demo, `ow_tp_` prefix). No jobs, no clusters, serverless warehouse `565cd2fd713738c4` only.
- CDC landing (parent workstream, D10-10): Debezium connector `ow_tp_dbz_ow_billing` on the 10 operational tables, Kafka topics -> `/Volumes/ow_tp/bronze/landing/cdc/` -> `ow_tp.bronze.cdc_*` -> apply into the batch branch.
- Fixture: `services/legacy-billing/db/oracle/setup/` seed reproduced in a Postgres fixture (`make tp-smoke` target) — children iterate on fixture, one live read per unit.

## 4. Execution schedule (as approved at STOP C, DEC-C)

STOP C added "Fix identity: grant SP on ow_tp, width 2 from wave 1". The parent provisioned the migration service principal
`dhrov_spa` (`2e90bc1d-e9a1-4703-8c48-ad28ebb1864d`, OAuth M2M); factory-doctor re-run 2026-09-14 is `ready=true`,
`blocking=[]`, so `migration-fanout/workflow.py` launches every wave. D10-11 closed. U4 calls `rating.sp_finalize_rating`
(U3), so it cannot run in the same wave as U3 (a child blocked on an unlanded sibling stops, it never builds a substitute);
U4 is therefore wave 3 on its own. Width is 2 from wave 1; only wave 1 actually has two batches.

| Wave | Batch | Units | Lakebase branch | Declared write targets | Size | verify_depth |
|---|---|---|---|---|---|---|
| 0 | w0-b1 | U0 (+ scaffolding above) | `mig-p1-w0-b1` | `ow_billing.util.*`, `ow_billing.codes/plans/tenants/billing_audit_log`, `ow_tp.silver.{codes,plans,tenants}`, `ow_tp.ops.p1_recon_runs` | M | sampled (all tables < threshold -> full diff anyway) |
| 1 | w1-b1 | U1 | `mig-p1-w1-b1` | `ow_billing.subscriptions`, `subscriptions_hist`, `plans.*`, `ow_tp.silver.subscriptions_hist` | M | full |
| 1 | w1-b2 | U2 | `mig-p1-w1-b2` | `ow_billing.usage_events`, `usage.*` | S | full |
| 2 | w2-b1 | U3 | `mig-p1-w2-b1` | `ow_billing.rating_periods`, `rating_results`, `rating.*` | L | full |
| 3 | w3-b1 | U4 (contract PR then implementation PR) | `mig-p1-w3-b1` | `ow_billing.invoices`, `invoice_lines`, `credit_notes`, `invoicing.*` | XL | full |

Same-wave batches (w1-b1, w1-b2) share no write target and no shared object beyond read-only U0 (checked by the workflow
before launch). Breaker 3 same-class failures. Legacy cap: 2 statements per unit; wave 1 uses 4 = the total cap.
Idempotency: each run drops and recreates the batch branch from its parent branch. `auto_merge: true` (stop_mode soft) but
merge requires verifier PASS. Pilot rule: wave 0 is a single unit.

Wall clock: 4 waves, serial floor 4 child rounds + 4 verifier passes; 6 PRs (U0, U1, U2, U3, U4-contract, U4). Lead times:
D10-9 (Lakehouse Sync, parent, "sync enabled") and D10-10 (CDC containers, parent, "cdc live") gate the recon posture only;
until those messages arrive Tier 6 is `skipped/no_cdc` and Delta copies are freeze-and-load. STOP E is gated by
D4-5/D3-1 (customer-owned).

Cost line: `dbx-recon estimate` needs unit mapping specs that do not exist before wave 0; from the analysis: 2 source
statements per unit, ~4-6 target statements per unit incl. parity tiers, < 1,000 rows total over the wire (largest table
814 rows), warehouse hours negligible (< 0.1 per wave). Wave 0 re-baselines waves 1-3 from actuals.

Manifests: `.migration/waves/wave-{0,1,2,3}.json`, `capabilities` copied from `09_capabilities.json` (SP identity).

## 5. Recon gate (mechanical)

Per unit, the child runs, from the plan and `.migration/` only:

1. `factory-doctor --role child --expect-identity <capabilities.identity> --expect-host <capabilities.host>`; any mismatch -> BLOCKED.
2. Convert into the batch branch; `make tp-smoke`, `make tp-validate-contracts`, `make tp-validate-schemas` green on fixture.
3. `dbx-recon run --mapping .migration/units/<unit>/mapping_spec.json --tolerances .migration/03_recon_tolerances.json --mode transactional --target-kind lakebase --depth full --run-mode fixture` until green; then **one** `--run-mode live` with source pinned `AS OF SCN` (pin recorded in `result.json`), target `REPEATABLE READ` on the branch.
4. PASS = tiers 1,2,3,5,7 `pass` with 0 unexplained row diffs; Tier 4 dual-run parity `pass` for every routine in the unit; Tier 6 `skipped` with reason `no_cdc` while D10-10 is open (recorded, not silent); `declared_source_rows` equals the census count at the pin (analysis §6 table); population per check = the whole table (no filters); baseline = Oracle at the pin, never fixture data.
5. Evidence on the PR: `result.json` (machine-readable, `make tp-validate-recon` green), the SCN pin, the branch name, fixture seed volumes, environment-ownership line, `run_mode` budget used (fixture N, live 1). Review-round cap 3, full re-run cap 3, then escalate.
6. Verifier (separate session) re-runs tiers 1+2 and Tier 3 at the wave's `verify_depth` against the same pin; only verifier PASS merges.

## 6. Governance mapping

Source has 0 object grants, 0 policies (`08_governance_inventory.md`), so the mapping is two PROPOSED rows and no GAP rows:

| Source row | Target statement | Status |
|---|---|---|
| `OW_BILLING` owner (implicit rights) | Lakebase role `ow_billing_app` owns schema `ow_billing`; `GRANT USAGE, EXECUTE` on all procedures | PROPOSED |
| `OW_BILLING_RO` (`SELECT ANY TABLE`) | Lakebase role `ow_billing_ro`: `GRANT SELECT ON ALL TABLES IN SCHEMA ow_billing`; UC: `GRANT SELECT ON SCHEMA ow_tp.silver TO <reports group>` (group to be named by customer — flagged) | PROPOSED |

Executable grant script is generated from APPROVED rows only, runs once in the parent against the migration branch;
production-branch grants are a STOP E action.

## 7. Risk register

Analysis §8 R1-R12 plus: **R13** (closed by DEC-C) fan-out workflow was unusable under the PAT identity; now `ready=true` as the SP; **R14** new-surface procedures (`close_billing_period`, `issue_credit_note`) have no source
truth — fixture Tier 4 only, flagged in each PR; **R15** `INVOICE_LINES` has 2 rows against 3 `INVOICES` at source — recon
compares as-is, no repair.
