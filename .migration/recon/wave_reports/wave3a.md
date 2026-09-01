# Wave 3a — Independent reconciliation report

- Session: [MONGO v1] Reconciliation & Parallel Run, Part 1 (independent; converted nothing
  in this wave; children's diagnoses not read before re-running)
- Date: 2026-09-01 (UTC)
- Run branch under review: `tp-run/mongodb-20260901T032752Z`
- Units: U5 invoicing (`tp-run/mongodb-20260901T032752Z--u5` @ b4ffa73f, PR #1411)
- Contracts: mapping spec v1.2 (approved), tolerances v1.0, canonicalization v1.2 — no
  tolerance touched by this session. (My brief cited v1.0; the branch carries the approved
  v1.1/v1.2 amendments already reconciled in the wave-2 report — none of their deltas touch
  U5's collections. Not drift.)
- Target: `ow_tp_mongodb_032752` (quarantine `ow_tp_mongodb_032752_quarantine`), Atlas
  secret `MONGODB_ATLAS_URI` (name only)
- Source: canonical Oracle fixture `otterworks-oracle-billing-oracle-billing-1`
  (localhost:52521/FREEPDB1, `OW_BILLING`) — found running and healthy, reused as-is, never
  reseeded or modified, left running. Single live window; gate, probes and replay run
  serially, `--source-concurrency 1`.

## Wave verdict: **PASS** (U5 PASS; zero gate findings; zero defects in probes/replay)

| Unit | Gate re-run (LIVE) | Adversarial probes | App-level replay | Verdict |
|---|---|---|---|---|
| U5 | Tier1 3/3, Tier2 11/11, Tier3 full diff (invoices 3 + lines embed 2, credit_notes 5) — PASS, 0 warnings | all green | all green (144/144 invoice_preview, 2/2 recorded transcripts, 4/4 invoice_lines; write path 8/8 unit tests) | **PASS** |

## 1. Gate re-run (verbatim, LIVE, authoritative)

From a worktree of the unit's own branch (`~/wave_recon/wt-u5` @ b4ffa73f), against its own
committed mapping generator: `bash scripts/tp-mongo-recon-u5.sh`. Harness output:
`recon PASS: unit=U5 mode=live mapping=1.2 tolerances=1.0` → **PASS, rc=0**.
Evidence: `wave3a_evidence/U5_gate_recheck/`. Tier 1 counts (invoices 3, invoices.lines 2,
credit_notes 5); Tier 2 11 per-field aggregates (tenant_id/period_id deferred to Tier 3);
Tier 3 full keyed diff over all 8 docs + embedded lines — zero findings, zero warnings.
No mismatch occurred, so no drift-vs-defect triage was required; source counts were
nonetheless read twice (stable: INVOICES 3, INVOICE_LINES 2, CREDIT_NOTES 5,
DUNNING_ATTEMPTS 1).

Declared subset, verified against the contract (not a gap): the approved spec's `invoices`
entry also declares a `dunning_attempts[]` embed. The gate excludes it via
`--exclude-embed invoices.dunning_attempts` because that array is **U6-owned**
(contract `.migration/contracts/U5.md`: U5 leaves the field absent; U6 populates it in the
sequential U5→U6 batch that owns `ow.invoices`). I verified the exclusion is recorded
verbatim in the emitted subset mapping and probed the deferred path directly (§2).

## 2. Adversarial probes (evidence: `wave3a_evidence/u5_probe.{py,out.json}`; my own code, not the harness)

- Counts (source read twice, stable): INVOICES 3 = invoices 3; INVOICE_LINES 2 = Σ
  `$size(lines)` 2; CREDIT_NOTES 5 = credit_notes 5.
- Duplicate keys: 0 dup IDs in INVOICES/CREDIT_NOTES; 0 dup (invoice_id, line_no).
- Orphan INVOICE_LINES: 0 (contract expects zero; confirmed at source).
- Null/missing per field: every mapped field in both collections — src NULL = tgt explicit
  null = 0, tgt missing-field 0 everywhere.
- Embed-array length distribution vs child rows: exact match per invoice
  ({inv-...001: 2}); the two lineless invoices carry explicit `lines: []` (2 docs), per
  contract; line order within the array strictly by `line_no`.
- Deferred U6 path: `dunning_attempts` present in **0** invoice docs (correctly absent, not
  empty-array); source DUNNING_ATTEMPTS has 1 row awaiting U6.
- Min/max boundary docs: invoices and credit_notes min/max `_id` identical on both stacks
  and present as docs (credit_notes ids span ...0001..0006 with one source-side gap — count
  5 on both stacks).
- Independent doc-level full compare (exact TO_CHAR decimal fetch, not the harness): all 3
  invoices incl. lines and all 5 credit_notes field-by-field — **0 mismatches**.
- Aggregate cross-checks on aggregate-only fields: Σ subtotal 347.00, Σ tax 28.62,
  Σ total 375.62; Σ credit amount 145.00, Σ remaining 145.00 — exact on both stacks.
- Schema shape: field universes exactly the mapped fields + `_id` + `ns` (+`lines`);
  `ns:"mongo_032752"` on 100% of docs; target db has exactly the 15 wave-0..3a collections;
  quarantine still only `invoice_feed_orphan_lines` (37, U2) — nothing stray.
- Indexes: invoices `(tenant_id, status_cd, issued_at)`; credit_notes
  `(tenant_id, issued_on)`; no unique `(period_id, tenant_id)` asserted — all per the
  contract's index plan.

## 3. Cross-unit consistency (shared references, both stacks)

- invoices.tenant_id → tenants._id: 0 orphans source, 0 target.
- invoices.period_id → rating_periods._id (U4): 0 orphans both stacks.
- credit_notes.tenant_id → tenants._id: 0 orphans both stacks.
- Codes decodability via wave-0 `codes`: invoice status distinct {20, 40} ⊂ INV_STATUS
  {10, 20, 30, 40}; distinct sets identical Oracle vs Mongo.

## 4. App-level query replay (evidence: `wave3a_evidence/u5_replay.{py,out.json}`)

Legacy SQL run verbatim from the `PKG_INVOICING` body (the package itself was never
invoked — `compute_preview` → `pkg_rating` → `pkg_ow_util.log_msg` is an
autonomous-transaction INSERT and the fixture must not be written; all arithmetic —
`ROUND`, `LEAST(cr, NVL(cap, cr))`, DECODE-exempt tax — was delegated to Oracle
`SELECT ... FROM dual` with binds) vs the branch's `InvoicingService` on Mongo:

| Operation | Cases | Parity |
|---|---|---|
| fn_invoice_preview (full 5-line rows, 7 cols) | 144: 3 real rating periods, all 65 tenants × 2 windows, no-such-tenant, 5 suspension-window cases | 144/144 EQUAL (incl. NULL-propagation rows for no-plan tenants and the credit-only cap-collapse branch) |
| Recorded Oracle transcripts `procs/oracle/transcripts/invoicing` INVOICE-001/002 (fn_invoice_preview, ground truth from the real package) | 2 | 2/2 EQUAL (both stacks match the recorded amounts/totals/line_types/tax_amount) |
| fn_invoice_lines SQL vs `invoice_lines` | 3 real invoice ids + 1 nonexistent | 4/4 EQUAL (incl. empty-result behavior) |
| Write path (sp_issue_invoice → `issue_invoice`) | out of read-only scope (fixture must not be written); branch's unit tests executed: `scripts/tp_mongo/tests/test_invoicing_service.py` | 8/8 passed (covers upsert-to-status-20, line rebuild atomicity, credit burn-down ordering, finalize_rating in-transaction per review round 1) |

Replay integrity note: 0 mismatches at any point; no scaffold corrections were needed
(the wave-2-validated read-only `compute_rating` replica was reused for the overage input).

## 5. Per-unit cost line

| Unit | Live-window wall time | Breakdown |
|---|---|---|
| U5 | ~9 min live window (gate ~1.5 min; probes ~2 min; replay ~4.5 min incl. one scaffold re-run; serial, source-concurrency 1) | plus ~0.5 min branch unit tests (no live source) |

## 6. Findings

1. **No defects.** Gate, probes, cross-unit joins and replay all clean.
2. `dunning_attempts[]` is a **declared deferral to U6**, not a gap: excluded from the gate
   subset per contract, verified absent (not empty) in every invoice doc; 1 source row
   waits for U6. U6's recon must include this embed — flagged for the U6/wave-3b gate.
3. Contract-version note repeated from wave 2: run executes under approved spec v1.2 /
   canonicalization v1.2; brief said v1.0. Explained drift of paperwork, not data.

---

# Wave-close brief — wave 3a (one page)

**Verdict: PASS.** U5 (invoicing: `invoices` + `lines[]` embed, `credit_notes`) passes its
LIVE recon gate re-run verbatim from the unit branch (Tier1 3/3, Tier2 11/11, Tier3 full
keyed diff, 0 findings, 0 warnings), all independent adversarial probes, cross-unit
referential checks against tenants/rating_periods/codes, and app-level replay: 144/144
`fn_invoice_preview` cases, 2/2 recorded Oracle transcripts, 4/4 `fn_invoice_lines` cases;
the write path (out of read-only scope) is covered by the branch's 8/8 unit tests, which
include the round-1 review fix (finalize_rating joins the issuance transaction; atomic
invoice upsert).

**Population honesty:** this unit's live population is tiny (3 invoices / 2 lines /
5 credit notes), so the gate's grade is mostly structural; the replay (144 preview cases
over all 65 tenants, incl. NULL-propagation, suspension proration and credit-cap-collapse
branches) is where the invoicing semantics actually got exercised — and it is exact.

**Deferral to carry forward:** `invoices.dunning_attempts[]` is U6-owned; U5 correctly
leaves the field absent and the gate correctly excludes it per contract. The wave-3b/U6
gate MUST grade that embed (1 source row today) — do not let the exclusion survive into U6.

**No tolerance was touched; no migrated or legacy code was modified.** Fixture left
running, unmodified. Evidence under `wave3a_evidence/`.
