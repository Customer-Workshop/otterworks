# Wave 3b — Independent reconciliation report

- Session: [MONGO v1] Reconciliation & Parallel Run, Part 1 (independent; converted nothing
  in this wave; children's diagnoses not read before re-running)
- Date: 2026-09-01 (UTC)
- Run branch under review: `tp-run/mongodb-20260901T032752Z`
- Units: U6 dunning (`tp-run/mongodb-20260901T032752Z--u6` @ 58a643a1, PR #1412)
- Contracts: mapping spec v1.2 (approved), tolerances v1.0, canonicalization v1.2 — no
  tolerance touched by this session. (Brief cites v1.0; the branch carries the approved
  v1.1/v1.2 amendments already reconciled in the wave-2/3a reports. Paperwork drift only.)
- Target: `ow_tp_mongodb_032752` (quarantine `ow_tp_mongodb_032752_quarantine`), Atlas
  secret `MONGODB_ATLAS_URI` (name only)
- Source: canonical Oracle fixture `otterworks-oracle-billing-oracle-billing-1`
  (localhost:52521/FREEPDB1, `OW_BILLING`) — found running and healthy, reused as-is, never
  reseeded or modified, left running. Single live window; gate, probes and replay run
  serially, `--source-concurrency 1`.

## Wave verdict: **PASS** (U6 PASS; zero gate findings; zero defects in probes/replay)

| Unit | Gate re-run (LIVE) | Adversarial probes | App-level replay | Verdict |
|---|---|---|---|---|
| U6 | Tier1 4/4, Tier2 10/10, Tier3 full diff (invoices 3 + lines 2 + dunning_attempts 1 embeds, notifications 1) — PASS, 0 warnings | all green | all green (20/20 fn_overdue_accounts LIVE cases, 5/5 recorded Oracle transcripts incl. write-path sandbox replay; 8/8 branch unit tests) | **PASS** |

## 1. Gate re-run (verbatim, LIVE, authoritative)

From a worktree of the unit's own branch (`~/wave_recon/wt-u6` @ 58a643a1), against its own
committed mapping generator: `bash scripts/tp-mongo-recon-u6.sh` with
`OW_BILLING_FIXTURE_DSN`/`MONGODB_ATLAS_URI` (names only). Harness output:
`recon PASS: unit=U6 mode=live mapping=1.2 tolerances=1.0` → `U6 | PASS | rc=0`.
Evidence: `wave3b_evidence/U6_gate_recheck/` (result.json + the emitted unit mapping).

- Tier 1 counts_through_mapping: 4 checks (invoices 3, invoices.lines 2,
  invoices.dunning_attempts 1, notifications 1) — pass.
- Tier 2 per-field aggregates: 10 checks; `invoices.tenant_id`, `invoices.period_id`,
  `notifications.tenant_id` deferred to Tier 3 per the `null_missing_equiv` convention.
- Tier 3 keyed diffs: full diff — invoices 3 docs with both embeds graded
  (`lines` 2, `dunning_attempts` 1), notifications 1 doc — 0 findings, 0 warnings.
- Wave-3a's declared deferral is now closed: the `dunning_attempts[]` embed U5 excluded
  (U6-owned) is included in this gate with **no exclusions**
  (`_recon_embed_exclusions: []`), and the emitted mapping is byte-identical to the
  approved spec v1.2 entries for `invoices` and `notifications` (verified
  programmatically, spec==emitted for both collections).

No mismatch occurred, so no drift-vs-defect triage was required; source counts were
nonetheless read twice and stable (NOTIFICATIONS 1, DUNNING_ATTEMPTS 1, INVOICES 3,
INVOICE_LINES 2).

## 2. Adversarial probes (evidence: `wave3b_evidence/probe_u6.{py,out.json}`; my own code, not the harness)

- Counts (source read twice, stable): NOTIFICATIONS 1 = notifications 1;
  DUNNING_ATTEMPTS 1 = Σ `$size(dunning_attempts)` 1 across invoices.
- Duplicate keys: 0 dup NOTIFICATIONS ids (src/tgt); 0 dup `(invoice_id, attempt_no)`.
- Orphan DUNNING_ATTEMPTS (child without parent invoice): 0 (contract: an orphan halts
  the load; confirmed zero at source).
- Null/missing per mapped field: src NULL 0 everywhere; tgt explicit-null 0 and
  missing-field 0 for all notification fields and all embed element fields.
- Embed-array length distribution vs source child rows: exact per invoice
  ({...002: 1}); the two attempt-less invoices carry the contract-required explicit
  `dunning_attempts: []` (not missing) — 0 invoices missing the field; array ordered by
  `attempt_no` (0 violations).
- Min/max boundary docs: notifications min/max `_id` identical on both stacks (single
  doc ...0001, present and field-equal).
- Independent doc-level full compare (exact TO_CHAR fetch, my own canonicalization):
  the notification doc and the dunning attempt element field-by-field vs Oracle —
  **0 mismatches**. `INVOICE_ID` correctly not stored on the element (parent key).
- U5 co-write integrity: U6's registered co-write touched only the array — invoice root
  fields intact (Σ subtotal 347.00 / tax 28.62 / total 375.62 exact on both stacks;
  `lines` embed re-graded clean by the gate).
- Schema shape: notifications field universe exactly `_id, tenant_id, kind_cd, sent_at,
  ns`; embed element universe exactly `attempt_no, id, tenant_id, scheduled_for,
  status_cd`; `ns:"mongo_032752"` on 100%; target db has exactly the 16 expected
  collections (15 prior + notifications); quarantine still only
  `invoice_feed_orphan_lines` (37, U2) — nothing stray.
- Indexes: notifications **unique** `(tenant_id, kind_cd, sent_at)` present (carries the
  `sp_suspend_overdue` dedup contract); invoices unchanged (no new index) — both per the
  U6 contract's index plan.
- Empty-collection behavior: impossible-filter reads return empty on both stacks;
  overdue scan for a far-past as_of returns 0 rows on both stacks (see replay).

## 3. Cross-unit consistency (shared references, both stacks)

- notifications.tenant_id → tenants._id: 0 orphans source, 0 target.
- dunning_attempts[].tenant_id → tenants._id: 0 orphans both stacks; attempt tenant ==
  parent invoice tenant for every row (0 disagreements at source).
- Codes decodability via wave-0 `codes`: notification kind distinct {2} ⊂ NOTIF_KIND;
  attempt status distinct {20} ⊂ DUN_STATUS; distinct sets identical Oracle vs Mongo.

## 4. App-level query replay (evidence: `wave3b_evidence/replay_u6.{py,out.json}`)

Read path LIVE on both stacks: `pkg_dunning.fn_overdue_accounts` invoked directly on the
fixture (SYS_REFCURSOR, read-only — no package write path reached) vs the branch's
`DunningService.overdue_accounts` on the live Mongo target.

| Operation | Cases | Parity |
|---|---|---|
| fn_overdue_accounts (full rows: tenant_id, invoice_id, total, days_overdue, tenant_status) | 20: all invoice issue dates ±1/±13/±14/±15 days, transcript date 2026-02-28, weekend days (SAT/SUN), far past (empty result), far future | 20/20 EQUAL (incl. strict `<` date-only boundary: as_of == issued day returns the row on neither stack; empty-result case equal) |
| Recorded Oracle transcripts `procs/oracle/transcripts/dunning` (ground truth from the real package) | 5 | 5/5 EQUAL |
| — DUNNING-001 fn_overdue_accounts business fields (days 27/15, tenants ...0002/...0005) | 1 | matched by the 2026-02-28 live case above |
| — DUNNING-002/003 sp_schedule_dunning → `schedule_dunning` (weekend shift SAT→+2; NVL(MAX)+1 next attempt on existing state) | 2 | 2/2 EQUAL — replayed in a mongomock sandbox seeded from the LIVE target (Atlas never written): full schedule_rows probe match, incl. duplicate-guard no-op semantics |
| — DUNNING-004/005 sp_suspend_overdue → `suspend_overdue` (14-day threshold; tenant+subs → 20; hist pre-image; conditional kind-3 notification; same-day rerun idempotent) | 2 | 2/2 EQUAL — suspension_notifications match verbatim (deterministic md5 id 8cd558f5-...); tenant ...0005 → status 20, its active subscription → 20 with suspended_on 2026-02-28, exactly 1 `subscriptions_hist` pre-image with `hist_op='UPD'` and pre-status 10; second run inserts 0 notifications (unique-index-backed NOT EXISTS port) |
| Write path against the live target | out of read-only scope (target and fixture never written by this session); branch unit tests executed: `scripts/tp_mongo/tests/test_dunning_service.py` | 8/8 passed |

Replay integrity note: 0 mismatches anywhere; transcripts' shared `oracle_source_sha`
matches the estate-level sha convention used by prior waves' transcripts (same value as
the wave-3a invoicing transcripts).

## 5. Per-unit cost line

| Unit | Live-window wall time | Breakdown |
|---|---|---|
| U6 | ~3 min live window (gate ~3 s; probes ~1 min; live read-path replay ~1.5 min; serial, source-concurrency 1) | plus ~0.5 min sandbox write replay + branch unit tests (no live source) |

## 6. Findings

1. **No defects.** Gate, probes, cross-unit joins and replay all clean.
2. Wave-3a follow-up **closed**: the U6 gate grades `dunning_attempts[]` with no
   exclusions; the 1 source row that was "awaiting U6" in wave 3a is now embedded and
   field-equal; attempt-less invoices carry the contracted explicit `[]`.
3. Declared, unexercised cross-unit follow-up (not a wave-3b defect): normalizing
   `dunning_attempts: []` on invoices *created after cutover* belongs to U5's
   `issue_invoice` (per the U6 contract); `schedule_dunning`'s guarded `$push` is correct
   either way — verified in the sandbox replay.
4. Contract-version note repeated: run executes under approved spec v1.2 /
   canonicalization v1.2; brief said v1.0. Explained paperwork drift, not data.

---

# Wave-close brief — wave 3b (one page)

**Verdict: PASS.** U6 (dunning: `notifications` + the `dunning_attempts[]` embed on
`ow.invoices`) passes its LIVE recon gate re-run verbatim from the unit branch
(Tier1 4/4, Tier2 10/10, Tier3 full keyed diff incl. both invoice embeds — 0 findings,
0 warnings), all independent adversarial probes, cross-unit referential checks against
tenants/codes, and app-level replay: 20/20 LIVE `fn_overdue_accounts` cases row-for-row
against the real Oracle package, 5/5 recorded Oracle transcripts (read and write paths;
write paths replayed in a mongomock sandbox seeded from the live target so neither Atlas
nor the fixture was written), and 8/8 branch unit tests.

**What was independently verified:** emitted unit mapping is byte-identical to approved
spec v1.2; unique `(tenant_id, kind_cd, sent_at)` index present on notifications (the
dedup contract carrier); explicit `dunning_attempts: []` on attempt-less invoices;
U5-owned invoice fields untouched by the co-write; weekend-shift, NVL(MAX)+1,
duplicate-swallow, 14-day suspension threshold, subscriptions_hist pre-image
(`hist_op='UPD'`), and same-day notification idempotency all behave identically to the
recorded Oracle ground truth. The wave-3a declared deferral of the dunning embed is now
closed with live evidence.

**Drift triage:** none needed — no gate mismatch; source counts read twice, stable.
**Cost:** ~3 min live source window (serial, cap 1) + ~1 min offline.
**Route:** nothing routes back to the orchestrator; fixture left running, unmodified.
Evidence: `.migration/recon/wave_reports/wave3b_evidence/`
(gate result + emitted mapping, `probe_u6.*`, `replay_u6.*`).
