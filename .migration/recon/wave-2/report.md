run_id: wfr-801c19c633a04d6d8886dc591a81877a
manifest_sha: 53d75305bc82

# Wave 2 independent recon (Part 1): PASS

Verifier session migrated nothing in this wave. Gates re-run from spec in this session; the PRs' pasted recon evidence was not used.
Spec: mapping map-1 (sha256 e6fda960...), tolerances v1 (sha256 03b3c6cc...), canonicalization profile oracle.md (mongo-migration plugin 0.3.2), manifest waves/wave-2.json (sha256 53d75305bc82...).
Access: source live, read-only OW_TP_ORACLE_RO_DSN, concurrency 1 (runs serialized); target migration_cluster, db ow_tp_mmp_live. No loader run, no target writes, no source writes.
Evidence is aggregate-only (counts, distributions, sums); no row values are reproduced. Harness output redacted (unsalted: RECON_REDACT_SALT not set).

| batch | unit | PR | head | own live gate | merge_eligible (harness) | verdict |
|---|---|---|---|---|---|---|
| w2-b01 | U2-invoices | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1745 | 759a91c0 | PASS | False (scoped embed) | PASS |
| w2-b02 | U3-billing-core | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1744 | b46bacb7 | PASS | True | PASS |
| w2-b03 | U4-app-backend | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1746 | ddafb31a | PASS | True | PASS |

Merged: none (manifest auto_merge=false and the verifier brief forbids merging). w2-b01 is not merge-eligible per its manifest flag and the harness (scoped embed); w2-b02 and w2-b03 are eligible for the workflow/human to merge.
Blocked: nothing. Breaker: no failures, nothing held back. Drift: none (no mismatch; source counts identical at start and end of probing).

## Gates (one live run per unit, serialized, 2026-09-29 20:00-20:04Z)
Common flags: `--family oracle --mapping .migration/03_mapping_spec.json --tolerances .migration/02_tolerances.json --canonicalization oracle.md --mode live --target-class migration_cluster --source-dsn-secret OW_TP_ORACLE_RO_DSN --target-uri-secret OW_TP_MMP_TARGET_URI --target-db ow_tp_mmp_live --allowed-targets-file .migration/allowed_targets.json --source-concurrency 1`, each run from a detached checkout of the PR head.
- U2-invoices `--collections invoices,quarantine_invoice_line` -> `recon PASS merge_eligible=False`; tier 1 counts 3/3, tier 2 aggregates 5/5, tier 3 keyed diffs 168750/168750 (18750 roots + 149963 lines + 37 quarantine); warning: `embed invoices.lines: scoped by a where-predicate; extra target elements not checked` (covered by probe below).
- U3-billing-core `--collections subscriptions,subscriptions_hist,usage_events,rating_periods,rating_results,billing_invoices,credit_notes,dunning_attempts,notifications,billing_audit_log` -> `recon PASS merge_eligible=True`; tier 1 11/11, tier 2 28/28, tier 3 901/901; no warnings.
- U4-app-backend `--collections codes,tenants,plans --ops services/legacy-billing/migration/U4-app-backend/ops.live.json` -> `recon PASS merge_eligible=True`; tier 1 3/3, tier 2 6/6, tier 3 104/104, tier 4 app parity 6/6 ops; no warnings.
No mismatch in any gate, so no source double-run was needed. Source counts (18 OW_BILLING tables) identical before and after the probe pass: source not moving.

## Probes past the gate (full-population, this session's own canonicalization, not the harness's diff code)
- invoices: 18750 source headers = 18750 docs, 0 missing, 0 extra, 0 duplicate _id; all 8 header fields and all 15 line fields compared on every doc/element: 0 mismatches, 0 BSON type errors, 0 fields outside the mapping.
- invoices.lines length distribution identical to per-header INVOICE_LINE counts for every one of 18750 invoices (0 length mismatches; 5 zero-line invoices, max 23 lines); line_id order (line_no, line_id) identical 18750/18750; 149963 embedded elements = 149963 attached source lines; 0 line_id embedded in more than one invoice. This closes the harness's scoped-embed gap: no extra target elements exist.
- Money: sum total_amt and sum lines.amount equal to the cent on both sides (exact decimal, Decimal128 in target).
- quarantine_invoice_line: 37 source orphan lines (no INVOICE_HEADER parent) = 37 docs, all fields equal, all tagged quarantine_reason=orphan_invoice_id / source_table=OW_BILLING.INVOICE_LINE; 0 quarantined lines also embedded in an invoice; 37 + 149963 = 150000 INVOICE_LINE rows, nothing dropped.
- U3 collections (billing_invoices 3, subscriptions 69, usage_events 814, rating_periods 3, rating_results 3, credit_notes 5, dunning_attempts 1, notifications 1): every row field-compared, 0 missing, 0 extra, 0 duplicate keys, 0 mismatches, 0 type errors. billing_invoices.lines length distribution identical (2 invoices with 0 lines, 1 with 2); 0 orphan INVOICE_LINES.
- Empty collections: subscriptions_hist and billing_audit_log are empty in source (0) and target (0), so their gate PASS is vacuous.
- Reference collections re-probed (codes 32, tenants 69, plans 3): 0 mismatches.
- Null/missing rates: for every mapped field source null count == target null/absent count; only non-zero ones are lines.posted_yn 29937, quarantine posted_yn 5, subscriptions.ends_on 69 (all), subscriptions.suspended_on 68.
- Indexes declared in the mapping spec exist on every wave-2 collection (0 missing).

## Cross-unit consistency
- invoices.cust_id -> customers (wave 1): 18750/18750 resolve in source and target. quarantine cust_id: 37/37 resolve.
- invoices.tenant_id -> tenants: 0 of 18750 resolve in source TENANTS and 0 in target, identical both sides (pre-existing source property, same as D-017 for customers).
- U3 internal and U3 -> wave-0 refs (subscriptions.plan_id, rating_results.subscription_id/period_id, billing_invoices.period_id, dunning_attempts.invoice_id, all tenant_id): 0 unresolved on either side.
- invoices (U2) and billing_invoices (U3) share no _id values (0 overlap); write targets are disjoint and U4 writes nothing to Atlas. Target db contains only mapped collections plus sequences (wave 0) and an empty _connectivity_probe.

## App-level parity replay
- ops.live.json (6 ops) replayed in the U4 gate's tier 4: PASS.
- ops.post-wave.json (7 ops over invoices, billing_invoices, subscriptions, customers: invoice status/type rollups, multi-line count, billing invoices and lines, subscription rows, admin balances) replayed with the harness tier-4 comparator against live Oracle and Atlas after all wave-2 loads: 7/7 PASS, 0 findings.
- U4 service suite against the local Mongo fixture (reproduces CI job legacy-billing-mongo): 45 passed, 0 failed, 0 skipped; test_mongo_parity.py 5/5 executed; bridge tests 6/6. Code checks: no float() on money, multi-document writes inside with_transaction, BILLING_READONLY honoured, default backend unchanged. ruff: 3 issues in test files only (F401 test_facade.py, E402 x2 test_mongo_parity.py), not CI-gated.

## Findings
- F1 (informational, source property): all 18750 invoice headers carry a tenant_id that does not exist in TENANTS in the source itself, and the migration preserves that exactly; consumers must not assume the invoice-to-tenant reference resolves.
- F2 (grading gap closed by probe): the harness cannot check for extra elements in the scoped invoices.lines embed, but the full-population probe found every invoice's lines array exactly equal to its source lines, so the not-merge-eligible flag on w2-b01 is structural, not a data defect.
- F3 (informational): subscriptions_hist and billing_audit_log are empty in the source, so their PASS proves only that the empty state migrated.
- F4 (cosmetic): U4's legacy-billing tests carry 3 ruff lint issues in test files; nothing in app code, not CI-gated.
- F5 (process): live harness output is still redacted with unsalted hashes because RECON_REDACT_SALT is not set.
- F6 (housekeeping): an empty _connectivity_probe collection from the STOP A probe remains in ow_tp_mmp_live.
