# 10_wave_plan: units, waves, width

Generated manifests: `.migration/waves/wave-{0,1,2,3}.json` (built by `waves/build_manifests.py`; validated with the migration-fanout `validate_manifest` + `check_write_targets` + fixture-manifest gate). Every manifest: `auto_merge: false`, `source_access: ddl_only`, `target_access: local`, width 3, breaker 3, fixture `.migration/fixtures/ow_billing_demo.json`.

## Units (12; every in-scope object from `09_coverage.md` is in exactly one)

| Unit | Pattern class | Collections (`ow_billing_migration.*`) | Fixture rows | XL |
|---|---|---|---|---|
| u-00-codes | reference (shared) | codes | 32 | |
| u-01-tenancy | plain + history_copy | tenants, plans, subscriptions, subscriptionsHist | 143 | |
| u-02-customers | wide-embed + attribute pattern, bulk-load | customerMaster (embeds ENTITY_ATTR_VALUE), customerMasterHist | 33,338 | **XL** (155 cols, CSV/list + dirty-date canonicalization) |
| u-03-invoicing-core | embed 1:few, transactional docs | invoices (embeds INVOICE_LINES), creditNotes, ratingPeriods, ratingResults | 19 | |
| u-04-usage-audit | append-only / ttl | usageEvents, billingAuditLog | 817 | |
| u-05-dunning-data | plain | dunningAttempts, notifications | 2 | |
| u-06-invoice-header-bulk | bulk-load embed 1:N + orphan quarantine | invoiceHeader (embeds INVOICE_LINE) | 168,750 | **XL** |
| u-07-plsql-util | proc-heavy (calibration) | — (parity_w3_b01 scratch) | 0 | |
| u-08-plsql-plans | proc-heavy (+2 triggers) | — | 0 | |
| u-09-plsql-rating | proc-heavy | — (parity_w3_b02 scratch) | 0 | |
| u-10-plsql-invoicing | proc-heavy | — | 0 | |
| u-11-plsql-dunning | proc-heavy + scheduled job | — | 0 | |

## Waves

| Wave | Batches | Units | Path | Expected cost |
|---|---|---|---|---|
| 0 | 1 | u-00-codes (shared/reference, serial) | single-session (`!mongo_unit_migration` here, then `!mongo_reconciliation` fresh) | 1 child ~20 min + verify ~15 min |
| 1 | 3 | u-01, u-02 (XL), u-03 — one calibration unit per data pattern class | `migration-fanout` workflow, width 3 | 3 × ~45 min + verify ~30 min |
| 2 | 3 | u-04, u-05, u-06 (XL) | `migration-fanout` workflow, width 3 | 30–50 % below wave 1 per unit (calibrated patterns); u-06 carries a decision-first contract PR |
| 3 | 2 | [u-07 (calibration), u-08], [u-09, u-10, u-11] | single-session (2 batches) | 2 × ~60 min + verify ~30 min; 30–50 % below wave 1 per unit after u-07 |

Single session vs fan-out: total fixture rows ≈ 203k (< 1M) but 12 units (> ~10), and the intake fixed fan-out width at 3, so the recommendation is: fan-out for the two 3-batch waves (1, 2), single-session for the 1- and 2-batch waves (0, 3), exactly as the orchestrator's batch-count rule says. Source concurrency 1 is moot here (no live source); children read only the local fixture.

Dependency depth: wave 0 (codes) → wave 1/2 data collections (no shared collections across batches within a wave; collision check passed) → wave 3 code units, which read collections from waves 0–2 and write only their declared `parity_<batch>` scratch collection.

Merge policy: no PR opened in this engagement may be merged (offline/local evidence; `auto_merge: false`; D-000). Wave-close messages list PASS PRs under "Awaiting manual merge"; they stay open pending customer-run live/snapshot recon against a migration cluster (D4-1, D4-2).
