# U6 pre-PR self-check evidence

Evidence produced for U6 against the deterministic `NS=demo` Oracle fixture. The
authoritative migration gate is `.migration/recon/U6/gate/result.json` (verdict PASS,
tiers 4/10/7); it was not rerun in this fix round.

This is a fixture-only child self-check: the source is the local deterministic,
read-only `NS=demo` Oracle fixture. The harness CLI models that with `--mode live`;
the parent runs the independent live gate.

- Harness tier 1 `counts_through_mapping`: **PASS** (4 checks).
- Harness tier 2 `per_field_aggregates`: **PASS** (10 checks).
- Harness tier 3 `keyed_diffs`: **PASS** (7 checks).

- [x] **NULL and missing attribution cannot fail open.** Missing tenants decode to
  `UNKNOWN`; unknown tenant, status, and notification codes are explicitly decoded
  rather than treated as known values. The loader halts on orphan attempts and
  duplicate `(INVOICE_ID, ATTEMPT_NO)` keys.
- [x] **Every catalog, schema, collection, and table reference is scoped.** U6 writes
  only `ow_tp_mongodb_032752.notifications` and the coordinated
  `ow_tp_mongodb_032752.invoices.dunning_attempts[]` field, with `ns` set to
  `mongo_032752`; the service rejects another database name.
- [x] **No DDL drops, replaces, or alters a shared table.** Drop-and-recreate is
  limited to the U6-owned `notifications` collection. The coordinated invoice
  update is additive-only and pre-authorized by the wave plan; Oracle access is
  SELECT-only.
- [x] **Retention and cleanup logic is safe on a rerun.** `load_u6.py` drops and
  recreates only `notifications`, and wholesale-sets only the dunning embed in
  U5-owned invoices. The embed load is idempotent.
- [x] **Cleanup paths retain run evidence and recon artifacts.** The parity
  restoration sequence reran `load_u0.py`, `load_u3.py`, `load_u5.py`, and
  `load_u6.py`; reports and gate artifacts remain under `.migration/recon/U6/`.
- [x] **No secrets, tokens, or real distribution-list/email addresses occur in
  source, evidence, or commit history.** Credentials are referenced by environment
  variable name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`).
- [x] **The parity-versus-tolerance decision matches the contract.** Transcript
  parity is compared value-for-value, while the independent recon gate uses mapping
  1.2 and tolerances 1.0.
- [x] **Idempotency was proven by an actual rerun.** `load_u6.py` was run twice and
  produced one notification and one embedded attempt on each run;
  `load_report.rerun.json` records the second run.
- [x] **Recon values were recomputed from the target platform.** The live harness
  read target MongoDB collections and graded full keyed diffs, including
  `invoices.dunning_attempts[]`; values were not copied from loader memory.
- [x] **Every unverified or untested path is listed below.**
- [x] **The machine-readable parity report declares `kind: recon-report`.**
- [x] **Capability preflight passed.** Oracle fixture connectivity, target MongoDB
  connectivity, loader execution, parity replay, and live recon all completed.
- [x] **`make tp-smoke` is green.**

## Coverage and reconciliation

- Root counts reconcile: `invoices` 3 and `notifications` 1.
- `invoices.dunning_attempts[]` is graded in tier 3 with **1 element** and **NO
  exclusion**. `invoices.lines[]` remains graded with 2 elements.
- The notification collection contains 1 document and has the unique
  `(tenant_id, kind_cd, sent_at)` index.
- All 5 dunning transcripts replayed **PASS**:
  `DUNNING-001` through `DUNNING-005`.
- The parity restoration sequence before every scenario was:
  `scripts/tp_mongo/load_u0.py`, then `load_u3.py`, then `load_u5.py`, then
  `load_u6.py`; sibling reports used scratch paths under `/tmp`.
- Load idempotency was proven by the actual second invocation recorded in
  `.migration/recon/U6/load_report.rerun.json`.
- The coordinated `ow.invoices.dunning_attempts[]` write is additive-only and
  pre-authorized by the migration wave plan; no other invoice field is touched.

## Declared unverified paths

- The source run is fixture-only: the local deterministic `NS=demo` Oracle fixture
  was used, not production Oracle.
- Real Oracle `PKG_DUNNING` PL/SQL procedures were not invoked; Oracle remained
  read-only and parity replay used the recorded transcripts against MongoDB.
- `JOB_NIGHTLY_DUNNING`'s scheduler was not activated; only its manual entrypoint
  was run.
- The `WHEN OTHERS THEN NULL` swallowed-write path was not induced against Atlas.
- Real Atlas transaction rollback under an injected failure was not induced; it is
  covered only by the mongomock transaction shim test.
- Runtime writes to U0/U3-owned `tenants` and `subscriptions` were exercised only
  during transcript replay.
- `UNKNOWN` status, notification-kind, and subscription-status code branches were
  not exercised by the deterministic fixture.
- The standalone job demo observed `suspended=0` because the preceding replay had
  already suspended tenant 5.

## Evidence artifacts

- `.migration/recon/U6/load_report.json`
- `.migration/recon/U6/load_report.rerun.json`
- `.migration/recon/U6/parity_dunning.json`
- `.migration/recon/U6/job_nightly_dunning.json`
- `.migration/recon/U6/mapping/u6.json`
- `.migration/recon/U6/gate/result.json`
- `.migration/recon/U6/gate/report.md`
- `.migration/recon/U6/gate/recon.summary.md`
