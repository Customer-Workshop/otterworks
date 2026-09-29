run_id: orchestrator-single-session-wave-1
manifest_sha: 7f1ffcf93906d73f

# Wave 1 independent recon (Part 1): PASS

Verifier session migrated nothing in this wave. Gate re-run from spec before reading any PR conversation.
Spec: mapping map-1 (sha256 e6fda960...), tolerances v1 (sha256 03b3c6cc...), canonicalization profile oracle.md (mongo-migration plugin 0.3.2).
Access: source live, read-only OW_TP_ORACLE_RO_DSN, concurrency 1; target migration_cluster, db ow_tp_mmp_live. No loader run, no target writes.
Evidence is aggregate-only; the only row values below are the DEMO-00000004 TAX_REGION_OVERRIDE facts named in the brief. Harness output redacted (unsalted: RECON_REDACT_SALT not set).

| batch | unit | PR | head | verdict |
|---|---|---|---|---|
| w1-b01 | U1-customers | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1743 | 55028dbb | PASS |

Merged: none (manifest auto_merge=false; merge decision left to the workflow/human).

## U1-customers: PASS

### Gate (one live run, 2026-09-29T18:52Z)
`recon run --unit U1-customers --family oracle --collections customers --mode live --target-class migration_cluster --source-concurrency 1`
-> `recon PASS mapping=map-1 tolerances=1 merge_eligible=True`; tier 1 counts 2/2, tier 2 aggregates 15/15, tier 3 keyed diffs 33333/33333 (25000 roots + 8333 attributes elements); duplicate source root keys 0; no warnings. No mismatch, so no source double-run needed.
Source counts identical at probe start and end (CUSTOMER_MASTER 25000, ENTITY_ATTR_VALUE 8333): source not moving.

### Probes past the gate
- attributes[] length distribution vs per-customer ENTITY_ATTR_VALUE (entity_type='CUSTOMER') counts, identical: len 0: 17925, 1: 5952, 2: 1000, 3: 113, 4: 8, 5: 2 (source and target). Per-customer count mismatches 0 of 25000; eav_id sequence per customer identical 25000/25000, all arrays ordered by eav_id; 8333 source rows = 8333 target elements; non-CUSTOMER EAV rows 0; EAV rows with no parent customer 0.
- Duplicates preserved: (customer, attr_name) groups with >1 row: source 187 groups / 379 rows, target 187 / 379.
- DEMO-00000004: exactly 1 target doc; 2 source EAV rows, 2 target elements, eav_ids and name/value pairs identical; TAX_REGION_OVERRIDE present twice with values `TRUE` and `1` (source order by eav_id: `TRUE`, `1`; target same).
- Null/missing rates per field: all 154 mapped fields, source non-null count == target present count (null/missing/empty equivalent per spec), 0 mismatching fields. Source null rates: 113 fields 100% null (absent in target as specified), 34 fields under 5% null, 7 fields between 15% and 75% null. attributes element fields attr_name/attr_value/attr_type/created_dt: 8333 non-null each side; max attr_value length equal.
- Keys and boundaries: 25000 docs, distinct _id 25000 (= distinct CUST_ID), distinct cust_no 25000 both sides, cust_seq_no min/max equal, CREATED_DT and UPDATED_DT min/max equal, 50 distinct tenant_id both sides. No target fields outside the mapping (+ _id, attributes); element fields exactly {eav_id, attr_name, attr_value, attr_type, created_dt}.
- Spot check (fields the gate only aggregates): 30 docs compared field-by-field on all 154 fields plus full attributes arrays, using this session's own canonicalization: 25 seeded-hash sample, zero-attribute customer, max-attribute (5) customer, min and max cust_seq_no, DEMO-00000004. 0 docs with any mismatch.
- Empty collections: customers 25000 (not empty).

### Cross-unit consistency
- customers.tenant_id -> tenants (wave 0): 50 distinct values, 0 resolve in target tenants and 0 resolve in source TENANTS (all 25000 rows). Identical on both sides: pre-existing source property, not a migration defect (finding F1).
- customers <-> EAV: 0 orphan EAV rows; every source customer has a doc, no target-only docs.

### App-level parity replay (literal app SQL on Oracle vs equivalent Mongo reads)
- facade customer lookup (first customer per tenant by cust_seq_no; cust_no, name, cur_bal_amt, past_due_amt, credit_hold_yn) over all 50 tenant_ids: 50 rows each, 0 differences.
- facade attributes lookup (EAV by entity_id ordered by eav_id) for the DEMO-00000004 tenant's first customer and all 30 spot-checked customers: identical to the embedded array.
- reports billing balance by conversion_batch_no (count, sum cur_bal_amt, sum past_due_amt): 1 group each, identical, exact decimal.

### Findings
- F1 (informational, source property, faithfully migrated): every customer's tenant_id is absent from TENANTS (50 distinct ids); tenant resolution relies on the app's ensure_tenant auto-provisioning. Later units joining customers to tenants must not assume the reference resolves.
- F2 (informational): 113 of 154 CUSTOMER_MASTER columns are entirely null in source and are absent from every target doc, as the null_missing_equiv rule specifies; apps reading them must treat missing as null.
- F3 (process): harness live output is redacted with unsalted hashes; set RECON_REDACT_SALT for later waves.
