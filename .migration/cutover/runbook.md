# Cutover runbook (DRAFT — not executable in this engagement)

Engagement: offline OW_BILLING (Oracle Free 23, `FREEPDB1`) -> MongoDB, run branch
`tp-run/mongodb-20260926T164803Z-rt-offline`. Prepared by playbook 5 step 4 while
`source_access=ddl_only` and `target_access=local` (`08_connectivity.json`). Every
production step below names the customer executor (customer DBA, cutover principal holder,
`00_context.md`). Devin never executes any of them (AGENTS.md rule 5).

## 0. Which paths repoint, which still read legacy (playbook 5 step 2)

Business-logic track: every PL/SQL object has converted logic that passed Tier 4 **in fixture
mode against the local target only**. Nothing has passed live/snapshot Tier 4 against a
migration cluster. Until the customer in-network run exists, **no path may repoint**; the
phase outcome on offer at STOP C is `read-consumer cutover` (readers D2-1, D2-3 and the
facade read paths first; writers and scheduled logic stay on Oracle), never `full retirement`.

| PL/SQL object (source) | Converted logic | Fixture/local Tier 4 | Live/snapshot Tier 4 | Still executing on source after cutover? |
|---|---|---|---|---|
| PKG_OW_UTIL | `migration/mongo/ow_util.py` (u-07, PR #1725) | PASS 2 ops | not run (offline) | yes until full retirement |
| PKG_PLANS + TRG_SUBSCRIPTIONS_HIST + TRG_SUB_NO_UNCANCEL | `plans_service.py` (u-08, PR #1725) | PASS 4 ops, 5/5 transcripts | not run | yes |
| PKG_RATING | `rating_service.py` (u-09, PR #1726) | PASS 2 ops, 8/8 transcripts | not run | yes |
| PKG_INVOICING | `invoicing_service.py` (u-10, PR #1726) | PASS 3 ops, 6/6 transcripts | not run | yes |
| PKG_DUNNING + JOB_NIGHTLY_DUNNING (`enabled => FALSE` in source) | `dunning_service.py::run_nightly_dunning` disabled by default (u-11, PR #1726) | PASS 3 ops, 5/5 transcripts | not run | yes (job stays disabled on both sides) |
| JOB_PURGE_AUDIT_LOG (`enabled => FALSE`) | TTL index 90 d on `billingAuditLog.createdAt` (u-04, PR #1722) | n/a | not run | yes (disabled) |
| TRG_CUSTOMER_MASTER_SEQ / _HIST, TRG_USAGE_EVENTS_CHECK | facade-side validation (u-02 #1716, u-04 #1722) | PASS | not run | yes |

## 1. Preconditions (all customer-executed, none met today)

1. Customer DBA provisions a read-only Oracle principal (D4-1) and a migration cluster
   (D4-2); records both by secret **name** in `06_access_checklist.md` via PR to the run branch.
2. Customer DBA runs the harness in-network for every unit u-00..u-11 with
   `--mode live|snapshot --target-class migration-cluster` against the approved spec
   `03_mapping_spec.json` (**map-draft-3.1**) and `02_tolerances.json` (**tol-2**), and commits
   result.json under `.migration/recon/customer-run/<unit>/` (redacted, harness default).
3. Every unit PR (#1708, #1710, #1711, #1712, #1716, #1721, #1722, #1724, #1725, #1726) is
   merged into the run branch **only on that live/snapshot evidence** (`merge_eligible=true`),
   then the run branch is promoted per the repo's tech-partnerships policy.
4. Customer supplies production row counts / snapshot manifest (D4-3) and confirms no
   out-of-repo Oracle reader (D2-4).
5. Human names: cutover window, freeze/watermark, rollback trigger, executor. Recommended
   below; none is decided.

## 2. Final delta catch-up (playbook 5 step 1) — customer DBA

1. Freeze: revoke INSERT/UPDATE on `OW_BILLING` from the billing app principal (or stop
   `services/legacy-billing` writers) at watermark `W = max(INVOICE_HEADER.created_at,
   USAGE_EVENTS.received_at, BILLING_AUDIT_LOG.created_at)` recorded to the second.
2. Incremental load: re-run each unit loader (`services/legacy-billing/migration/mongo/load_*.py`,
   `fixture_load.py` collections) in upsert mode with `--since W-1d`; loaders are idempotent
   (deterministic `_id`s, D-0xx).
3. Full recon at exactly `W`: `recon run --mode live --target-class migration-cluster
   --watermark W` per unit; all tiers PASS; keyed diffs 0 beyond the recorded quarantines
   (u-02: 63 dirty values; u-06: 37 orphan lines) — anything else aborts cutover.

## 3. Repoint (read-consumer cutover) — customer DBA / customer billing team

| Step | Consumer | Change | Executor | Verify immediately after |
|---|---|---|---|---|
| 3.1 | `services/legacy-billing/app` facade reads | set `BILLING_BACKEND=mongo`, `MONGO_URI=<secret MONGO_MIGRATION_URI by name>` in the service config; rolling restart | customer billing team | `GET /internal/health` reports backend `mongo`; parity probe `procs/harness` vs Oracle on 20 sampled tenants: 0 mismatches |
| 3.2 | `reports.py` month-end/customer reports (D2-1) | same flag | customer billing team | month-end report for the last closed period byte-identical to the Oracle run |
| 3.3 | CUSTBILL extract (D2-3) | switch `etl/legacy-extra/tools/oracle_custbill_extract.py` source to the Mongo-backed extract | customer data team | feed row count and checksum equal for the last batch_no |
| 3.4 | writers (PKG_* callers, `/internal/usage/events`) | **stay on Oracle** in this phase | — | — |
| 3.5 | JOB_NIGHTLY_DUNNING / JOB_PURGE_AUDIT_LOG | stay disabled on both sides | — | — |

Verification queries (run by Devin once the customer confirms 3.1-3.3, playbook 5 step 6):
per-collection `countDocuments` vs Oracle `COUNT(*)` at `W`; `recon run` first-cycle in live
mode; facade `/invoices/{id}` for 100 sampled ids vs Oracle facade JSON.

## 4. Rollback — customer DBA (rollback owner)

- Trigger (recommended): any verification query in section 3 mismatching, or a first-cycle
  recon FAIL, within 24 h of step 3.1.
- Procedure: unset `BILLING_BACKEND=mongo` (back to `oracle`), rolling restart; re-point the
  CUSTBILL extract to Oracle. No data movement is needed because writers never left Oracle
  in this phase.
- Point of no return: the first write repointed to MongoDB (not part of this phase). Until
  then rollback is configuration-only.
- Rollback must be rehearsed as a procedure in the customer's staging before the window.

## 5. Post-cutover / decommission (playbook 5 step 7) — into `05_decisions.md` when it happens

Oracle stays writable (writers remain) and readable for the rollback window; no package,
trigger or job is dropped in this phase; Devin's fixture credentials
(`OW_BILLING_FIXTURE_DSN`, `MONGO_LOCAL_URI`) are demo constants and hold no production access.
