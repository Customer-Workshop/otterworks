run_id: orchestrator-single-session-wave-0
manifest_sha: 5566065a557939b9

# Wave 0 independent recon (Part 1): PASS

Verifier session migrated nothing in this wave. Gate re-run from spec before reading any PR conversation.
Spec: mapping map-1 (sha256 e6fda960...), tolerances v1 (sha256 03b3c6cc...), canonicalization profile oracle.md (mongo-migration plugin 0.3.2).
Access: source live, read-only OW_TP_ORACLE_RO_DSN, concurrency 1; target migration_cluster, db ow_tp_mmp_live. No loader run, no target writes.
Evidence is aggregate-only; no production row values. Harness output redacted (unsalted: RECON_REDACT_SALT not set).

| batch | unit | PR | head | verdict |
|---|---|---|---|---|
| w0-b01 | U0-reference | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1742 | f70db00e | PASS |

Merged: none (manifest auto_merge=false; merge decision left to the workflow/human).

## U0-reference: PASS

### Gate (one live run, 2026-09-29T18:50Z)
`recon run --unit U0-reference --family oracle --collections codes,tenants,plans --mode live --target-class migration_cluster --source-concurrency 1`
-> `recon PASS mapping=map-1 tolerances=1 merge_eligible=True`; tier 1 counts 3/3, tier 2 aggregates 6/6, tier 3 keyed diffs 104/104; no warnings. No mismatch, so no source double-run needed.
Source counts identical at probe start and end (CUSTOMER_MASTER 25000, ENTITY_ATTR_VALUE 8333, TENANTS 69, PLANS 3, CODES 32): source not moving.

### Probes past the gate
- Key sets: tenants 69 src / 69 tgt, symmetric difference 0; plans 3/3, diff 0; codes 32/32, composite (code_type, code_val) distinct 32 in target, diff 0. No duplicate keys.
- Null/missing rates: tenants (name, tax_exempt_yn, status_cd), plans (code, tier_cd, monthly_fee, included_units, overage_rate, active_yn), codes (code_type, code_val, code_desc) all fully populated on both sides; non-null counts equal field by field; 10 distinct code types both sides.
- Lookup integrity: tenants whose status_cd has no TENANT_STATUS code: 0 source, 0 target.
- Sequences (not in mapping spec, unverified by harness): DBA_SEQUENCES owner OW_BILLING = 5 (ALL_SEQUENCES visible to RO user = 0, as expected). Target `sequences` = 5 docs, 0 extra, 0 missing; last_number and increment_by match 5/5. For the 2 sequences whose backing table has rows (customer_master cust_seq_no, entity_attr_value eav_id) target last_number > current max backing id; the other 3 back empty tables.
- Empty collections: none in scope (codes 32, tenants 69, plans 3, sequences 5). `_connectivity_probe` (0 docs) is harness connectivity residue, not a migration collection.

### Cross-unit consistency
- subscriptions.plan_id: 3 distinct, 0 unresolved against target plans. subscriptions.tenant_id: 69 distinct, 0 unresolved against target tenants. invoices.tenant_id: 3 distinct, 0 unresolved. subscriptions_hist: empty.
- customers.tenant_id (wave 1) and invoice_header.tenant_id: 50 distinct values each, none present in TENANTS, identically in source and target. Pre-existing source property (see finding F1), not a U0 defect.

### App-level parity replay (literal app SQL on Oracle vs equivalent Mongo reads)
- pkg_plans.fn_list_plans (active plans, tier decode, order by monthly_fee, code): 3 rows each, identical.
- ensure_tenant default plan pick (cheapest active by monthly_fee, id): identical.
- facade tenant summary (tenants LEFT JOIN codes TENANT_STATUS) over all 69 tenants: 0 row differences.
- USAGE_KIND code lookup (lower(code_desc) by code_val): 3 rows each, identical.

### Findings
- F1 (informational, source property, faithfully migrated): no CUSTOMER_MASTER row and no INVOICE_HEADER row has a TENANT_ID present in TENANTS (50 distinct ids each); the app tolerates this via ensure_tenant auto-provisioning. Wave 2+ units that embed or join tenant data must not assume the reference resolves.
- F2 (process): harness live output is redacted with unsalted hashes; set RECON_REDACT_SALT for later waves so low-entropy flags/codes are not enumerable.
