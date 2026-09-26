run_id: local-wave0-1790443360
manifest_sha: 6476a1749fa3

# Wave 0 independent recon report

Verifier session wrote none of the wave. Gates re-run from spec (`.migration/mapping/<unit>.json` v1.0.0, `.migration/02_tolerances.json` v1.0.0, oracle profile canonicalization), not from PR-pasted output. Connectivity per `.migration/08_connectivity.json`: `source_access: live`, `target_access: migration_cluster`. Nothing was reloaded; no write to the cluster; Oracle access was SELECT only.

Wave verdict: **PASS**. Manifest `auto_merge: true`, but this verifier did not merge (instructed to return verdicts only).

## Per-batch verdicts

| Batch | Units | PR | Verdict | Mode / target class | merge_eligible |
|---|---|---|---|---|---|
| w0-b01 | shared-reference | [#1709](https://github.com/Cognition-Partner-Workshops/otterworks/pull/1709) | **PASS** | live / migration_cluster | true |

## w0-b01 / shared-reference

### Step 1: gate re-run (independent)
Command (from worktree root, `recon/wave-0`):
`recon run --unit w0-b01 --family oracle --mapping .migration/mapping/shared-reference.json --tolerances .migration/02_tolerances.json --canonicalization <oracle.md> --mode live --target-class migration_cluster --source-dsn-secret ORACLE_BILLING_RO_DSN --target-uri-secret MONGODB_MMP_RT_TARGET_URI --target-db mmp_rt_billing --allowed-targets-file .migration/allowed_targets.json --source-concurrency 1 --seed 20260926 --out .migration/recon/wave-0/w0-b01/shared-reference/`

Result (`w0-b01/shared-reference/result.json`, generated 2026-09-26T17:23:11Z, redacted+salted):

| Tier | Checks | Result |
|---|---|---|
| 1 counts_through_mapping | 3 | PASS (codes 32, tenants 70, plans 3) |
| 2 per_field_aggregates | 8 | PASS (6 string fields deferred to tier 3 by design) |
| 3 keyed_diffs | 105 | PASS (full_diff on all three collections, 0 duplicate source keys) |

verdict=PASS, merge_eligible=true, warnings=[], error=null. Counts agree with the child's evidence in PR #1709 (32/70/3); no source re-read needed because there was no mismatch (no drift observed).

### Step 2: probes past the gate (read-only, pymongo + Oracle SELECT)
- Null / missing per mapped field: 0 missing, 0 null on every target field of codes (3 fields), tenants (4), plans (7); Oracle source has 0 NULL / empty-string values on the same columns, so null_missing_equiv is not exercised.
- Duplicate keys: 0 in codes (`{codeType,codeVal}`), tenants (`_id`), plans (`_id`).
- Empty collections: none (32 / 70 / 3 docs; source row counts identical).
- Indexes vs mapping index_plan: tenants `{name:1} unique` present, plans `{code:1} unique` present, codes has `_id_` only (index_plan lists none for codes). Matches spec.
- Boundary / referential: every non-null `tenants.statusCd` resolves to a `codes` doc with codeType TENANT_STATUS (0 orphan refs). 10 code types present (CUST_STATUS, CUST_TYPE, DUN_STATUS, INV_STATUS, NOTIF_KIND, PHONE_TYPE, PLAN_TIER, SUB_STATUS, TENANT_STATUS, USAGE_KIND).
- Document shape: tenants/plans carry both `_id` and the mapped `id` field, as the mapping declares (key target `_id`, field target `id`).
- Embeds: none in this unit (all three collections are flat).

### Step 3: cross-unit consistency
Wave 0 has one batch and one unit; no cross-batch references exist yet. codes/tenants/plans are the shared reference collections that waves 1+ will reference; their keys are unique and complete, so later units can rely on them.

### Step 4: app-level parity replays (my own queries, not the child's summary)
- `pkg_plans.fn_list_plans` (Oracle: `WHERE NVL(active_yn,'N')='Y' ORDER BY monthly_fee, code` with DECODE tier label) vs mongo `plans.find({activeYn:true}).sort(monthlyFee, code)` + app-side tier label: 3 rows each, tuples (plan_id, code, tier, monthly_fee, included_units, overage_rate) equal after Decimal normalisation.
- facade tenant summary (`TENANTS LEFT JOIN CODES ON code_type='TENANT_STATUS' AND code_val=status_cd`) replayed for all 70 tenants against `backends/mongo/shared_reference.tenant_summary` logic (two point reads): 0 missing tenants, 0 mismatches in (name, status, tax_exempt Y/N).

### PR hygiene
PR #1709 diff vs merge-base touches only `services/legacy-billing/app/backends/mongo/{__init__,shared_reference}.py`, `services/legacy-billing/migration/{common,load_shared_reference}.py`, and `.migration/recon/w0-b01/shared-reference/{result.json,report.md,recon.summary.md}`. No other `.migration/` file changed; no mapping or tolerance edits; no legacy source modified.

## Findings
1. Batch w0-b01 (shared-reference) PASSES independent live recon against the migration cluster with merge_eligible=true and all 116 checks green.
2. Probes past the gate found no nulls, missing fields, duplicate keys, empty collections, or orphan TENANT_STATUS references in codes, tenants, or plans.
3. Both application parity replays (fn_list_plans and the tenant summary join for all 70 tenants) return identical results from Oracle and MongoDB.
4. The unique indexes required by the mapping index_plan (tenants.name, plans.code) exist on the loaded collections.
5. PR #1709 is eligible to merge under the manifest's auto_merge=true; this verifier did not merge it per instructions.

## Skill feedback (for the wave brief)
- The child's feedback stands: `recon run` grades every collection in `--mapping`, so per-unit mapping views are required to scope a batch; and root_table must be schema-qualified for an RO principal without synonyms.
- Harness note: tier 2 defers all string min/max/distinct_count to tier 3; on small reference tables this is fine, but the summary table should state that explicitly so a reader does not read "8 checks" as full field coverage.
