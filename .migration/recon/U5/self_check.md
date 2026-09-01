# U5 pre-PR self-check evidence

Evidence produced for U5 against the deterministic `NS=demo` Oracle fixture. The
authoritative migration gate is `.migration/recon/U5/gate/result.json` (verdict PASS,
tiers 3/11/10); it was not modified.

This is a fixture-backed run: the source is the local deterministic read-only
`NS=demo` Oracle fixture. The harness CLI models that with `--mode live` (its modes are
`live`, `snapshot`, `continuous`), and the U5 wrapper ran the independent live gate.

- Harness tier 1 `counts_through_mapping`: **PASS** (3 checks).
- Harness tier 2 `per_field_aggregates`: **PASS** (11 checks).
- Harness tier 3 `keyed_diffs`: **PASS** (10 checks).

- [x] **NULL and missing attribution cannot fail open.** The service defaults a missing
  tenant exemption flag to `N`, preserves explicit nulls, propagates null plan/usage
  arithmetic, and restricts reads and writes to the registered target database and
  namespace. Orphan invoice lines abort the loader.
- [x] **Every catalog, schema, collection, and table reference is scoped.** The loader
  writes only `ow_tp_mongodb_032752.invoices` and `.credit_notes`, with `ns` set to
  `mongo_032752`; the service rejects another database name.
- [x] **No DDL drops, replaces, or alters a shared table.** Drop-and-recreate is limited
  to the two U5-owned MongoDB collections. Oracle access is SELECT-only.
- [x] **Retention and cleanup logic is safe on a rerun.** The loader drops and recreates
  only the two owned collections and leaves recon artifacts outside those collections.
- [x] **Cleanup paths retain run evidence and recon artifacts.** The parity restoration
  sequence reran `load_u4.py` and `load_u5.py`; reports and gate artifacts remain under
  `.migration/recon/U5/`.
- [x] **No secrets, tokens, or real distribution-list/email addresses occur in source,
  evidence, or commit history.** Credentials are referenced by environment-variable name
  only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`).
- [x] **The parity-versus-tolerance decision matches the contract.** Transcript parity
  is compared value-for-value, while the independent recon gate uses mapping 1.2 and
  tolerances 1.0.
- [x] **Idempotency was proven by an actual rerun.** `load_u5.py` was run twice and
  produced the same 3 invoices, 2 embedded lines, and 5 credit notes on each run;
  `load_report.rerun.json` records the second run.
- [x] **Recon values were recomputed from the target platform.** The live harness read
  the target MongoDB collections and graded full keyed diffs rather than using loader
  memory or prior reports.
- [x] **Every unverified or untested path is listed below.**
- [x] **The machine-readable parity report declares `kind: recon-report`.**
- [x] **Capability preflight passed.** Oracle fixture connectivity, target MongoDB
  connectivity, loader execution, parity replay, and live recon all completed.
- [x] **`make tp-smoke` is green.**

## Coverage and reconciliation

- Root counts reconcile: `invoices` 3, `credit_notes` 5.
- Embedded `invoices.lines[]` reconciles with 2 source rows and is value-graded in tier
  3; `dunning_attempts[]` is excluded as an approved U6-owned deferred embed.
- All 6 invoicing transcripts replayed **PASS**:
  `INVOICE-001` through `INVOICE-006`.
- The parity replay's mutation restoration sequence was:
  `scripts/tp_mongo/load_u4.py`, then `scripts/tp_mongo/load_u5.py`.
- Contracted indexes are present:
  `invoices(tenant_id, status_cd, issued_at)` and
  `credit_notes(tenant_id, issued_on)`.

## Declared unverified paths

- The run is fixture-only: the source is the local deterministic `NS=demo` Oracle
  fixture, not production Oracle.
- `invoices.dunning_attempts[]` is excluded and deferred to U6 because it is U6-owned,
  sequential-batch work.
- The audit-log write is suppressed: `pkg_ow_util.log_msg` targets
  `BILLING_AUDIT_LOG`, which U7 owns. The service preserves the audit sink seam, but the
  actual audit collection write is not exercised.
- The no-plan/missing-plan preview path is covered by unit tests but is not one of the
  six recorded Oracle transcripts.
- Transaction rollback/error recovery and malformed source-value branches are not
  exercised by the deterministic fixture.

## Evidence artifacts

- `.migration/recon/U5/load_report.json`
- `.migration/recon/U5/load_report.rerun.json`
- `.migration/recon/U5/parity_invoicing.json`
- `.migration/recon/U5/gate/result.json`
- `.migration/recon/U5/gate/report.md`
- `.migration/recon/U5/gate/recon.summary.md`
- `.migration/recon/U5/mapping/u5.json`
