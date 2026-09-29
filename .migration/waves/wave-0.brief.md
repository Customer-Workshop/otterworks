# Wave 0 close

Exceptions: 0.
Landed: 1 of 1 batches passed their own live recon; 1 merge-eligible.
Independent verify (fresh session): PASS.
Failed: none.
Blocked on missing inputs: none.
Held back by circuit breaker: none.
Awaiting manual merge (auto_merge=false, D-004/D-015): https://github.com/Cognition-Partner-Workshops/otterworks/pull/1742

Verifier findings:
- Fresh live gate for U0-reference passed (counts 3/3, aggregates 6/6, keyed diffs 104/104, merge_eligible=True); the source did not move during the run.
- Key sets, non-null counts and composite code keys for codes, tenants and plans match source exactly, with no duplicate keys and no empty collections.
- All 5 OW_BILLING sequences in DBA_SEQUENCES match the target sequences docs on last_number and increment_by.
- Subscription plan_id/tenant_id and invoices tenant_id references resolve against the migrated plans and tenants.
- All 50 distinct customer/invoice_header tenant_id values are absent from TENANTS in both source and target: a carried-over source property, not a defect.
- Replayed app queries (plan list, default plan, tenant summary, USAGE_KIND lookup) are identical on Oracle and Mongo.
- Harness live output is redacted with unsalted hashes because RECON_REDACT_SALT is not set.

PROFILE FEEDBACK: none.

Per batch:
- w0-b01: PASS. codes/tenants/plans/sequences loaded live; live recon PASS (T1 3/3, T2 6/6, T3 104/104), merge-eligible; idempotent rerun 0 upserts/0 deletes. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1742
