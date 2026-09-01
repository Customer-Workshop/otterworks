# Wave 0 — Independent reconciliation report

- Session: [MONGO v1] Reconciliation & Parallel Run, Part 1 (independent; converted nothing in this wave)
- Date: 2026-09-01 (UTC)
- Run branch under review: `tp-run/mongodb-20260901T032752Z`
- Units: U0 (`tp-run/mongodb-20260901T032752Z--u0`, PR #1397)
- Contracts: mapping spec v1.0, tolerances v1.0, canonicalization v1.0
- Target: `ow_tp_mongodb_032752` (quarantine `ow_tp_mongodb_032752_quarantine`), Atlas secret `MONGODB_ATLAS_URI` (name only)
- Source: canonical Oracle fixture `otterworks-oracle-billing-oracle-billing-1`
  (localhost:52521/FREEPDB1, `OW_BILLING`) — reused running container, never reseeded,
  left running. Single live window; all gates run serially, `--source-concurrency 1`.

## Wave verdict: **DRIFT-EXPLAINED** (functionally PASS; zero defects found)

| Unit | Gate re-run (LIVE) | Adversarial probes | App-level replay | Verdict |
|---|---|---|---|---|
| U0 | Tier1 4/4 PASS, Tier2 12/12 PASS, Tier3 104/106 PASS — 2 findings, both on `fixture_meta` declared-unexercised key | all green | all green | **DRIFT-EXPLAINED** |

## 1. U0 gate re-run (verbatim, LIVE, authoritative)

Invocation: `scripts/tp-mongo-recon-u0.sh` (verbatim harness call: `recon run --unit U0
--family oracle --mapping <generated u0.json> --tolerances .migration/02_tolerances.json
--canonicalization .migration/recon_canonicalization.json --mode live
--source-dsn-secret OW_BILLING_FIXTURE_DSN --target-uri-secret MONGODB_ATLAS_URI
--target-db ow_tp_mongodb_032752 --source-concurrency 1 --seed 0`).
Harness: mongo-recon-harness skill v0.2.0; `recon selftest` PASS (9 canonicalization rules).

Result (evidence: `wave0_evidence/U0_gate_recheck/`):
- Tier 1 counts_through_mapping: 4 checks PASS (codes 32, tenants 69, plans 3, fixture_meta 1).
- Tier 2 per_field_aggregates: 12 checks PASS.
- Tier 3 keyed_diffs: full diff on all four collections; **2 findings, both `fixture_meta`**:
  - `missing_doc key=2026-09-01 03:28:46.978` (source-side value on THIS canonical fixture)
  - `extra_doc key=2026-09-01 04:54:35.780` (value loaded by the U0 child)

### Drift-vs-defect triage → DRIFT, fully explained

- Source re-run twice (2s apart): `FIXTURE_META.INITIALIZED_AT` stable at
  `2026-09-01 03:28:46.978908` both times → no source instability.
- The canonical container on this machine started `03:28:42Z`; `INITIALIZED_AT` is
  `SYSTIMESTAMP` written at fixture init. The child's load (05:00:05Z per its
  `load_report.json`) captured `04:54:35.780` — the init timestamp of the fixture
  instance in the child's own environment. Same deterministic seed, different
  instance-local bookkeeping timestamp.
- The approved mapping spec v1.0 already anticipates exactly this: `fixture_meta` is
  `parity: count_only` with `INITIALIZED_AT` in `declared_unexercised`
  ("SYSTIMESTAMP at fixture init is non-deterministic; amendment approved 2026-09-01",
  03_mapping_spec.md:53 and 03_mapping_spec.json). Count parity holds (1 = 1).
- The loader (`scripts/tp_mongo/load_u0.py:145-148`) correctly copies the source value
  verbatim (ms-truncated) — no code defect.
- **Harness observation (PROFILE FEEDBACK, not a unit defect):** the harness keyed-diffs
  collections even when the mapping declares `parity: count_only` /
  `declared_unexercised`, so any environment with a different fixture-init timestamp will
  Tier-3-flag `fixture_meta` despite the approved amendment. No tolerance was adjusted;
  no migrated code was touched.

All 104 non-fixture_meta Tier-3 checks (codes 32, tenants 69 full diff, plans 3 full
diff) PASS with zero findings.

## 2. Adversarial probes (evidence: `wave0_evidence/probe_u0.{py,out.json}`)

- Null/missing distribution, per field (12 fields across tenants/plans/codes): source
  null counts = 0 everywhere; target null = 0, target missing = 0. NULL/missing
  distinction preserved (no field silently dropped).
- Duplicate keys: 0 duplicate source keys (TENANTS.ID, PLANS.ID, composed
  CODE_TYPE||'#'||CODE_VAL); 0 duplicate `_id` in all four target collections.
- Min/max boundary docs: tenants min `_id` `00000000-...-0001` and max `_id`
  `fd52ea22-...-5289` verified doc-level field-by-field — PASS. All 3 plans verified
  doc-level including Decimal128 `monthly_fee` (2dp) and `overage_rate` (6dp)
  against Oracle NUMBER — exact.
- Full value diff of `codes` (all 32 docs, all fields + composed `_id`): 0 mismatches,
  0 extras. Composed-key amendment implemented correctly (explicit `code_val` retained).
- Schema shape: 0 docs with stray/missing fields vs the U0 contract; `ns:"mongo_032752"`
  present and correct on 100% of docs in all four collections.
- Empty-collection / quarantine behavior: `ow_tp_mongodb_032752_quarantine` has no
  collections (correct — U0 has no orphan population); target db contains exactly the
  4 U0 collections, nothing else.
- Embed-array probes: N/A — U0 has no embeds by contract.
- Indexes: only default `_id_` on all four collections. The index plan's U0-relevant
  promise ("codes: unique _id") is satisfied by the `_id` index itself. Note for later
  waves: no secondary indexes exist yet on tenants/plans (none are required by the U0
  contract; subscriptions/customers indexes belong to their own units).

## 3. Cross-unit consistency (shared references)

- `tenants.status_cd` distinct set identical on both sides and 100% decodable via
  `codes` `TENANT_STATUS#<val>` docs.
- `plans.tier_cd` values 100% decodable via `PLAN_TIER#<val>` docs.
- Code-type histogram identical Oracle vs Mongo (10 types: CUST_STATUS 4, CUST_TYPE 3,
  DUN_STATUS 3, INV_STATUS 4, NOTIF_KIND 3, PHONE_TYPE 4, PLAN_TIER 3, SUB_STATUS 3,
  TENANT_STATUS 2, USAGE_KIND 3) — later units (invoices, subscriptions, dunning,
  notifications, usage) will find every decode row they need.

## 4. App-level query replay (evidence: `wave0_evidence/replay_u0.py`)

Replayed the wave's representative operations on both stacks, myself:

| Operation (citation) | Oracle | Mongo | Parity |
|---|---|---|---|
| `fn_list_plans` (pkg_plans.sql:20-33): active plans, tier decode, ORDER BY monthly_fee, code | 3 rows | 3 docs | EQUAL (values incl. decimals) |
| `f_code_desc` (pkg_util.sql:34-45): decode all 32 (code_type, code_val) pairs | 32 | 32 | 0 mismatches; unknown code → no doc (matches no-row behavior) |
| reports.py STATUS_SQL decode arm: INV_STATUS lookup table | 4 rows | 4 docs | EQUAL |
| entitlement/dunning tenant-side lookup (fn_entitlement `t.id = :tenant_id`): all 69 tenants point-lookup + TENANT_STATUS decode | 69 | 69 | 0 failures |

## 5. Per-unit cost line

| Unit | Independent recon cost (this session) |
|---|---|
| U0 | 1 live gate re-run (~6 s harness wall time, 106 checks) + 2 source triage re-reads + 1 probe pass + 1 replay pass; single live window, serial; ≈15 min session wall time incl. environment setup (recon venv install). No Atlas/source writes. |

## 6. Findings summary

1. **DRIFT-EXPLAINED (only finding):** `fixture_meta._id` differs across fixture
   instances because `INITIALIZED_AT` is instance-local `SYSTIMESTAMP`. Covered by the
   approved 2026-09-01 amendment (count-only parity, declared-unexercised). Count parity
   holds. No action required for the wave; any future full-estate recon on a fresh
   fixture will reproduce this cosmetic Tier-3 finding until the harness honors
   `parity: count_only` (profile feedback filed in this report, §1).
2. Zero data defects, zero code defects, zero tolerance issues found in U0.
3. Fixture left running, unmodified, never reseeded.

---

# Wave 0 close brief (one page)

**Wave:** 0 (U0 shared-reference: codes, tenants, plans, fixture_meta).
**Independent verdict: DRIFT-EXPLAINED — functionally PASS; no defects; safe to open Wave 1.**

- The U0 gate was re-run verbatim in LIVE mode against the canonical Oracle fixture on
  the parent machine. 110/112 total checks green across Tiers 1-3; the only 2 findings
  are the `fixture_meta` init-timestamp key, which the approved mapping amendment
  explicitly declares unexercised (count-only parity, which holds 1=1). Source-side
  double re-read confirmed the source is stable: this is environment drift between the
  child's fixture instance and the canonical one, not a load defect.
- Adversarial probing beyond the gate (null/missing per field, duplicate keys, boundary
  docs, full doc-level value diffs on codes/plans, schema-shape, ns-stamp, quarantine
  emptiness) found nothing.
- Cross-unit reference integrity for the whole run is intact: every status/tier decode
  the later units depend on exists and matches, with identical code-type histograms.
- App-level replay (fn_list_plans, f_code_desc over all 32 codes, INV_STATUS decode
  table, 69 tenant point-lookups with status decode) shows exact result parity.
- Risks carried forward: (a) harness does not honor `parity: count_only`, so
  `fixture_meta` will re-flag on any fresh fixture — profile feedback, do not patch
  ad-hoc; (b) no secondary indexes exist yet — correct for U0's contract, but Wave 1+
  units must create the ones the index plan assigns to their collections.
- Nothing routed back to the orchestrator; no fixes, tolerance changes, or legacy edits
  were made by this session.
