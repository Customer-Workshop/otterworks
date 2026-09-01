# U2 pre-PR self-check evidence

Evidence produced for U2 against the deterministic `NS=demo` Oracle fixture. The
authoritative migration gate is `.migration/recon/U2/gate/result.json` (verdict PASS,
tiers 2/8/168713); it was not modified.

- [x] **Root and embedded counts reconcile.** The harness passed 2 tier-1 checks:
  `invoice_feed` has 18,750 roots and 149,963 embedded `lines[]` elements.
- [x] **Mapped field values reconcile.** The harness passed all 8 tier-2 aggregate
  checks and all 168,713 tier-3 keyed-diff checks, including value grading for all
  149,963 embedded line elements.
- [x] **Orphans are quarantined, not silently dropped.** Supplemental evidence records
  149,963 matched lines, 37 orphan lines, and 150,000 total source lines; embedded plus
  quarantined equals the source total.
- [x] **Orphan identity is exact.** The 37 Oracle orphan `LINE_ID` values equal the
  quarantine `_id` set; no IDs are missing or unexpected, and every quarantine document
  has `reason_class=orphan_fk`, `unit=U2`, and `ns=mongo_032752`.
- [x] **Report behavior is preserved.** Supplemental report parity passed row-for-row:
  3 status rows and 12 line rows for batch `85559852`, with no differing rows.
- [x] **Every migrated document is namespace tagged.** Load assertions report 18,750
  namespace-tagged roots and 37 namespace-tagged quarantine documents.
- [x] **The loader is idempotent.** The rerun dropped and recreated only the two owned
  collections and produced the same 18,750 roots, 149,963 embedded lines, and 37
  quarantine documents with no doubling. Both recon gates passed with identical tier
  counts.
- [x] **Only the registered Mongo targets are written.** Oracle access is SELECT-only;
  writes are limited to `ow.invoice_feed` and `owq.invoice_feed_orphan_lines`.
- [x] **No secrets are included in source or evidence.** Credentials are referenced by
  environment-variable name only (`OW_BILLING_FIXTURE_DSN`, `MONGODB_ATLAS_URI`).
- [x] **No ungraded embedded values.** `gate/result.json` has no UNGRADED warning; the
  embedded line key and fields are declared in the approved mapping.
- [x] **Application seam is covered.** Month-end status and line reports use the migrated
  Mongo collection; reconciliation remains Oracle-backed through U1's `customer_master`.
- [x] **`make tp-validate-recon` is green for `U2.recon.json`.**

## Declared unverified paths

- The `UNKNOWN(status_cd)` `$ifNull` branch is not exercised: all seeded headers map to
  `INV_STATUS` 20, 30, or 40.
- The `UNKNOWN(line_type_cd)` `$switch` default is not exercised: the fixture contains
  only line types 1, 2, 3, and 9.
- All-NULL `SUM` group semantics are not exercised: `amount`, `tax_amt`, `total_amt`,
  `qty`, and `unit_price` are never NULL in this fixture; Oracle NULL and Mongo zero
  therefore remain unverified for an all-NULL group.
- This is fixture-only evidence (`run_mode=fixture`); the wave gate runs LIVE
  independently.
- The reconciliation endpoint remains Oracle-backed through U1's `customer_master`;
  U2 does not migrate that path.

## Evidence artifacts

- `.migration/recon/U2/load_report.json`
- `.migration/recon/U2/load_report.rerun.json`
- `.migration/recon/U2/gate/result.json`
- `.migration/recon/U2/gate/report.md`
- `.migration/recon/U2/gate/recon.summary.md`
- `.migration/recon/U2/gate_rerun/result.json`
- `.migration/recon/U2/supplemental.json`
