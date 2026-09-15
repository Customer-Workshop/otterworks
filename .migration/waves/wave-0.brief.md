# Wave 0 close — reference data (U1-reference)

**0 exceptions. PASS.** One batch, run in-session per the small-wave rule; live recon is the
merge authority.

Loaded into `ow_billing_migration`: 3 plans, 32 codes, 69 tenants with 69 embedded
subscriptions, 0 subscription history rows (the source table is empty). Counts were
recomputed from Atlas, not carried over from the load.

- Recon: `.migration/recon/U1-reference/U1-reference.recon.json` (fixture PASS, then one live
  run PASS; tiers 1-4, 173 keyed diffs, no sampling, 0 findings).
- Idempotency: a second load with no drop left every collection byte-identical
  (`.migration/recon/U1-reference/idempotency.json`).
- Preflight: `.tp-preflight/atlas-capabilities.json`, passed, cited in every wave 1 brief.

**Not covered, stated plainly.** The harness has no rule for Y/N-to-boolean, CSV-to-array or
`DD-MON-YY`-string-to-date, and no way to compare an integer code against its decoded string,
so those fields are graded by tier 4 operations rather than the canonicaliser. The repo
self-check wants an `ow_tp` namespace prefix; the intake fixes the target database as
`ow_billing_migration`, so the allowlist is the control instead. `subscription_history` has no
rows, so its field grading is structural only.

**Amendment (grading-only, pre-authorised at STOP A).** `codes` compares on
(`codeType`, `codeVal`) rather than the composed `_id`, which the harness cannot match against
a two-column source key. The PRD identity is unchanged.

**The anomaly budget is untouched by this wave.** All 37/50/31 anomalies live in
`CUSTOMER_MASTER` and `INVOICE_LINE`, which are wave 1.

Next: wave 1, four batches, `migration-fanout` at width 4.
