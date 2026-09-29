# Wave 1 close

Exceptions: 0.
Landed: 1 of 1 batches passed their own live recon; 1 merge-eligible.
Independent verify (fresh session): PASS.
Failed: none.
Blocked on missing inputs: none.
Held back by circuit breaker: none.
Awaiting manual merge (auto_merge=false, D-004/D-015): https://github.com/Cognition-Partner-Workshops/otterworks/pull/1743

Verifier findings:
- Fresh live gate for U1-customers passed (counts 2/2, aggregates 15/15, keyed diffs 33333/33333, merge_eligible=True); the source did not move during the run.
- attributes[] length distribution and per-customer eav_id sequence match ENTITY_ATTR_VALUE (CUSTOMER) exactly: 0 mismatches over 25000 customers, 8333 = 8333 elements.
- Duplicate attribute names are preserved: 187 groups covering 379 rows on both sides.
- DEMO-00000004 carries TAX_REGION_OVERRIDE twice (TRUE and 1) in source and target.
- For all 154 mapped fields source non-null count equals target present count; no duplicate _id or cust_no; boundary values match; no unmapped target fields.
- A 30-document field-by-field spot check (sample, boundary docs, DEMO-00000004) found 0 mismatches.
- All 50 customers.tenant_id values are unresolved against tenants in source and target: a carried-over source property.
- Replayed app queries (first customer per tenant, attributes lookup, balances by conversion batch) are identical on Oracle and Mongo.

PROFILE FEEDBACK: none.

Per batch:
- w1-b01: PASS. 25,000 customers with 8,333 attribute elements loaded live; live recon PASS (T1 2/2, T2 15/15, T3 33,333/33,333), merge-eligible; idempotent rerun 0/0. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1743
