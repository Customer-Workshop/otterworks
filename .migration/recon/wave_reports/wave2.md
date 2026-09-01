# Wave 2 — Independent reconciliation report

- Session: [MONGO v1] Reconciliation & Parallel Run, Part 1 (independent; converted nothing in this wave; children's diagnoses not read before re-running)
- Date: 2026-09-01 (UTC)
- Run branch under review: `tp-run/mongodb-20260901T032752Z`
- Units: U3 subscriptions (`tp-run/mongodb-20260901T032752Z--u3` @ 363ac50c, PR #1409),
  U4 rating (`--u4` @ 95aa9553, PR #1408),
  U7 audit-util (`--u7` @ 48524dbd, PR #1407)
- Contracts: mapping spec v1.2 (U3, approved amendment) / v1.1 (U4, U7), tolerances v1.0,
  canonicalization v1.2 (U3) / v1.1 (U4, U7) — see §1 note; no tolerance touched by this session
- Target: `ow_tp_mongodb_032752` (quarantine `ow_tp_mongodb_032752_quarantine`), Atlas secret `MONGODB_ATLAS_URI` (name only)
- Source: canonical Oracle fixture `otterworks-oracle-billing-oracle-billing-1`
  (localhost:52521/FREEPDB1, `OW_BILLING`) — found running and healthy, reused as-is,
  never reseeded or modified, left running. Single live window; all gates + probes +
  replay run serially, `--source-concurrency 1`.

## Wave verdict: **PASS** (all three units PASS; zero gate findings; zero defects in probes/replay)

| Unit | Gate re-run (LIVE) | Adversarial probes | App-level replay | Verdict |
|---|---|---|---|---|
| U3 | Tier1 2/2, Tier2 15/15, Tier3 69/69 full diff — PASS, 0 warnings | all green | all green (list_plans, 213 entitlement cases) | **PASS** |
| U4 | Tier1 3/3, Tier2 15/15, Tier3 820/820 full diff — PASS, 0 warnings | all green | all green (78 usage_summary + 31 compute_rating cases incl. suspension proration) | **PASS** |
| U7 | Tier1 1/1, Tier2 3/3, Tier3 0-population full diff — PASS, 0 warnings | all green (empty=empty, TTL index correct) | n/a (no read query; write path is out of read-only scope, unit-tested on branch) | **PASS** (declared write-path divergence noted, §6.2) |

## 1. Gate re-runs (verbatim, LIVE, authoritative)

Each gate was run from a worktree of the unit's own branch, against its own committed
code + mapping generator, in the single serial live window:

- U3: `bash scripts/tp-mongo-recon-u3.sh` (worktree `--u3` @ 363ac50c). Harness output:
  `recon PASS: unit=U3 mode=live mapping=1.2 tolerances=1.0` → **PASS, rc=0**.
  Evidence: `wave2_evidence/U3_gate_recheck/`. Counts (subscriptions 69;
  subscriptions_hist 0), 15 per-field aggregates (9 deferred to Tier 3 per the approved
  v1.2 amendment), Tier-3 full keyed diff over all 69 docs — zero findings.
- U4: `bash scripts/tp-mongo-recon-u4.sh` (worktree `--u4` @ 95aa9553). Harness output:
  `recon PASS: unit=U4 mode=live mapping=1.1 tolerances=1.0` → **PASS, rc=0**.
  Evidence: `wave2_evidence/U4_gate_recheck/`. Counts (usage_events 814; rating_periods 3;
  rating_results 3), 15 per-field aggregates (4 deferred to Tier 3), Tier-3 full keyed
  diff over all 820 docs — zero findings.
- U7: `bash scripts/tp-mongo-recon-u7.sh` (worktree `--u7` @ 48524dbd). Harness output:
  `recon PASS: unit=U7 mode=live mapping=1.1 tolerances=1.0` → **PASS, rc=0**.
  Evidence: `wave2_evidence/U7_gate_recheck/`. Count 0=0 (BILLING_AUDIT_LOG is genuinely
  empty at source — verified directly, twice), 3 per-field aggregates, Tier-3 full diff
  over the empty population. An empty population graded by tiers 1–3 is the whole grade
  this data can carry; the collection + TTL index existence was probed separately (§2).

Contract-version note (not drift): my brief cited contracts v1.0; the branches carry the
user-APPROVED amendments (05_decisions.md): v1.1 (U1-era, CUSTOMER_MASTER only — no effect
on this wave's collections) and v1.2 (U3: `null_missing_equiv` on SUBSCRIPTIONS.ENDS_ON /
SUSPENDED_ON, Tier-2 aggregate deferral only; bson_type stays date; data contract
unchanged). U3 correctly runs under v1.2; U4/U7 branched at v1.1, whose delta doesn't touch
their collections. No mismatch occurred anywhere, so no drift-vs-defect triage was
required; source counts were nonetheless read twice each (stable: 69/0/814/3/3/0).

## 2. Adversarial probes (evidence: `wave2_evidence/probe_wave2.{py,out.json}`; my own code, not the harness)

- Counts: src SUBSCRIPTIONS 69 = subscriptions 69; SUBSCRIPTIONS_HIST 0 =
  subscriptions_hist 0 (collection exists, empty); USAGE_EVENTS 814 = usage_events 814;
  RATING_PERIODS 3 = rating_periods 3; RATING_RESULTS 3 = rating_results 3;
  BILLING_AUDIT_LOG 0 = billing_audit_log 0 (collection exists, empty). Each source count
  read twice, stable.
- Duplicate keys: 0 duplicate IDs at source in all four keyed tables; 0 duplicate
  (tenant_id, period_start) natural keys in RATING_PERIODS.
- Null/missing per field: for every mapped field in subscriptions, usage_events,
  rating_periods, rating_results — target explicit-null count equals source NULL count
  and target missing-field count is 0 everywhere. The v1.2 amendment columns:
  ends_on 69/69 NULL, suspended_on 68/68 NULL + the 1 non-null value exact (see §6.3).
- Independent doc-level full compare (not the harness): all 69 subscriptions, all 814
  usage_events, all 3 rating_periods, all 3 rating_results compared field-by-field with
  exact decimal fetch — **0 mismatches** across 889 docs.
- Min/max boundary docs: subscriptions and usage_events min/max `_id` identical on both
  stacks and present as docs.
- Aggregate cross-checks: Σ usage units 336,293 = 336,293; Σ overage_amount 0 = 0.00;
  subscription status histogram {10:68, 20:1} identical; usage kind histogram
  {1:504, 2:149, 3:161} identical.
- Embed arrays: none in this wave's collections (all 1:1) — n/a by design.
- Schema shape: field universes contain nothing beyond the mapped fields + `_id` + `ns`;
  `ns:"mongo_032752"` on 100% of docs in all six collections; target db contains exactly
  the 13 wave-0/1/2 collections, nothing stray; quarantine still only
  `invoice_feed_orphan_lines` (37, from U2).
- Indexes: subscriptions `(tenant_id, starts_on)` (latest-covering lookup);
  usage_events `(tenant_id, occurred_at, kind_cd)`; rating_results `(period_id)`;
  billing_audit_log TTL `ttl_logged_at_90d` on `logged_at` with
  `expireAfterSeconds=7776000` (= 90 days, replacing JOB_PURGE_AUDIT_LOG) — all per the
  index plan.

## 3. Cross-unit consistency (shared references, both stacks)

- subscriptions.tenant_id → tenants._id: 0 orphans source, 0 target (unlike the
  customers/invoice fixture horror, this join is healthy — and identically healthy).
- subscriptions.plan_id → plans._id: 0 orphans both stacks.
- usage_events.tenant_id → tenants._id: 0 orphans both stacks.
- rating_results.period_id → rating_periods._id and rating_results.subscription_id →
  subscriptions._id: 0 orphans both stacks.
- Codes decodability via wave-0 `codes`: subscription status distinct {10,20} ⊂
  SUB_STATUS {10,20,30}; usage kinds {1,2,3} = USAGE_KIND {1,2,3}; distinct sets
  identical Oracle vs Mongo.

## 4. App-level query replay (evidence: `wave2_evidence/replay_wave2.{py,out.json}`)

Legacy SQL run verbatim from the PL/SQL bodies (the packages themselves were never
invoked — pkg_plans/pkg_rating call `pkg_ow_util.log_msg`, an autonomous-transaction
INSERT, and the fixture must not be written) vs each unit's own migrated service module
imported from its branch:

| Operation | Cases | Parity |
|---|---|---|
| fn_list_plans SQL vs U3 `plans_service.list_plans` | 3 active plans, full row compare incl. Decimal128 fee/rate | EQUAL |
| fn_entitlement SQL vs U3 `plans_service.entitlement` | all 69 subscription tenants + 2 nonexistent tenants × 3 dates = 213 | 213/213 EQUAL (incl. empty-result behavior) |
| fn_usage_summary SQL vs U4 `RatingService.usage_summary` | 25 tenants + 1 nonexistent × 3 windows (incl. an empty 2020 window) = 78 | 78/78 EQUAL |
| compute_rating (PL/SQL math replicated read-only) vs U4 `RatingService.compute_rating` | 31 cases: the 3 real rating periods, 25 tenant/window combos, and 3 targeted windows over the single suspended subscription (proration branch) | 31/31 EQUAL |

Replay integrity note: two initial "mismatches" were both artifacts of my replay scaffold,
not of the migrated code — (a) `Decimal('1E+2')` vs int 100 normalization; (b) my Oracle
math replica used banker's rounding where Oracle `ROUND(x,2)` is half-away-from-zero.
(b) was settled by asking Oracle itself:
`SELECT ROUND(ROUND(101*0.035 + 99*0.035*1.5, 2) * (14/28), 2) FROM dual` → 4.37, exactly
what U4's service returns. After fixing my scaffold: 0 failures.

## 5. Per-unit cost line

| Unit | Independent recon cost (this session) |
|---|---|
| U3 | 1 live gate re-run (86 checks, <1 min wall) + probe share (nulls×6 fields, dup keys, boundaries, 69-doc full compare, index check) + list_plans/entitlement replay ×216; serial single live window; no writes to source or target. |
| U4 | 1 live gate re-run (838 checks, ~1 min wall) + probe share (nulls×… all fields, 820-doc full compare, histograms, xrefs ×4) + usage_summary ×78 and compute_rating ×31 replay incl. the suspension-proration edge; no writes. |
| U7 | 1 live gate re-run (4 checks over the empty population, <1 min) + probes (0=0 twice, collection + TTL-index existence/expiry check); replay n/a (write-only surface); no writes. |

Session total ≈ 30 min wall; fixture container reused (was already running), left running.

## 6. Findings summary

1. Zero data defects, zero code defects, zero tolerance issues in U3, U4 or U7. All three
   gates PASS live with 0 findings and 0 warnings; no drift to triage.
2. U7 declared divergence (documented in `.migration/contracts/U7.md` on the branch,
   informational here): the ported `log_msg` accepts module >30 bytes / message >4000
   bytes that the legacy `ORA-06502 + WHEN OTHERS` silently discarded — audit acceptance
   is strictly wider; no event the source kept is changed. Migrated *data* parity is
   unaffected (source table empty; empty=empty verified). Not a recon defect; flagged for
   the orchestrator's awareness since acceptance-widening is a behavioral (not data)
   divergence and is already declared on the PR.
3. Observation (informational): the v1.2 amendment text describes SUSPENDED_ON as
   "all-NULL", and U3's progress row says "all-NULL in NS=demo" (the child's fixture);
   the canonical fixture has exactly 1 non-null SUSPENDED_ON (tenant
   `...-000000000002`, 2026-02-15). Parity for that value is exact on both stacks
   (Tier-3 full diff + my own doc compare + the targeted proration replay), and the
   amendment's Tier-2 deferral is grading-only, so nothing changes — recorded so the
   decision-log wording isn't mistaken for a live-data assertion.
4. BILLING_AUDIT_LOG genuinely has 0 rows at source (verified twice, directly); the U7
   collection exists empty with the correct 90-day TTL index. Empty-collection behavior
   is correct on the target.
5. Fixture container found running and healthy; reused, never reseeded or modified, left
   running.

---

# Wave 2 close brief (one page)

**Wave:** 2 (U3 subscriptions: `ow.subscriptions` + `ow.subscriptions_hist`; U4 rating:
`ow.usage_events` + `ow.rating_periods` + `ow.rating_results`; U7 audit-util:
`ow.billing_audit_log` + TTL purge replacement).
**Independent verdict: PASS — all three units; safe to open Wave 3 (U5 → U6).**

- All three unit gates were re-run VERBATIM in LIVE mode on the canonical Oracle fixture
  from each unit's own branch: U3 86/86 checks PASS (mapping v1.2, the approved
  ends_on/suspended_on aggregate-deferral amendment), U4 838/838 PASS (mapping v1.1),
  U7 4/4 PASS over a genuinely empty source table. Zero findings, zero warnings, no
  drift-vs-defect triage needed; source reads were repeated with stable results.
- Adversarial probing beyond the gates found nothing: independent field-by-field compare
  of all 889 migrated docs exact; NULL→explicit-null (never missing) on every field;
  no duplicate keys; boundary docs exact; usage/status histograms and decimal sums exact;
  no stray fields or collections; all contract indexes present, including the 90-day TTL
  on billing_audit_log (expireAfterSeconds=7776000).
- Cross-unit references are fully healthy on both stacks: subscriptions→tenants/plans,
  usage_events→tenants, rating_results→rating_periods/subscriptions all 0 orphans;
  SUB_STATUS and USAGE_KIND codes 100% decodable via wave-0 `codes`.
- App-level replay: 322 replayed operations (list_plans, 213 entitlement lookups, 78
  usage summaries, 31 rating computations including the single suspended subscription's
  proration windows) — exact result parity between the legacy SQL/PL/SQL semantics and
  the units' Mongo services. Two transient mismatches were my replay scaffold's own
  artifacts, settled against Oracle itself (ROUND is half-away-from-zero).
- Carried forward: (a) U7's declared, documented behavioral divergence — audit acceptance
  strictly wider than the legacy ORA-06502 silent-drop path (data parity unaffected);
  (b) subscriptions_hist and billing_audit_log write paths are exercised only by unit
  tests until Wave 3's proc-heavy flows drive them; (c) decision-log wording nit on
  SUSPENDED_ON "all-NULL" (fixture has 1 value; parity exact).
- Nothing routed back to the orchestrator; no fixes, tolerance changes, or legacy edits
  were made by this session.
