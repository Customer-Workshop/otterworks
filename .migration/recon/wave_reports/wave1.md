# Wave 1 — Independent reconciliation report

- Session: [MONGO v1] Reconciliation & Parallel Run, Part 1 (independent; converted nothing in this wave; children's diagnoses not read before re-running)
- Date: 2026-09-01 (UTC)
- Run branch under review: `tp-run/mongodb-20260901T032752Z`
- Units: U1 customers (`tp-run/mongodb-20260901T032752Z--u1`, PR #1406),
  U2 invoice-feed (`tp-run/mongodb-20260901T032752Z--u2`, PR #1398)
- Contracts: mapping spec v1.1 for U1 / v1.0 for U2 (see §1 note), tolerances v1.0,
  canonicalization v1.1 (U1) / v1.0 (U2)
- Target: `ow_tp_mongodb_032752` (quarantine `ow_tp_mongodb_032752_quarantine`), Atlas secret `MONGODB_ATLAS_URI` (name only)
- Source: canonical Oracle fixture `otterworks-oracle-billing-oracle-billing-1`
  (localhost:52521/FREEPDB1, `OW_BILLING`) — container was stopped on arrival; restarted
  with `docker start` (never recreated, never reseeded), left running. Single live
  window; both gates + all probes run serially, `--source-concurrency 1`.

## Wave verdict: **PASS** (both units PASS; zero findings in either gate; zero defects in probes/replay)

| Unit | Gate re-run (LIVE) | Adversarial probes | App-level replay | Verdict |
|---|---|---|---|---|
| U1 | Tier1 3/3, Tier2 311/311, Tier3 33,333/33,333 — all PASS, 0 warnings | all green | all green | **PASS** |
| U2 | Tier1 2/2, Tier2 8/8, Tier3 168,713/168,713 — all PASS, 0 warnings | all green | all green | **PASS** |

## 1. Gate re-runs (verbatim, LIVE, authoritative)

Each gate was run from a worktree of the unit's own branch, against its own committed
code + mapping generator, in the single serial live window:

- U1: `bash scripts/tp-mongo-recon-u1.sh` (worktree `--u1` @ cf527ee4). Harness output:
  `recon PASS: unit=U1 mode=live mapping=1.1 tolerances=1.0` → **PASS, rc=0**.
  Evidence: `wave1_evidence/U1_gate_recheck/`. 3 count checks (customers 25,000;
  customer_master_hist 0; embedded attributes 8,333), 311 per-field aggregates, 33,333
  keyed diffs — zero findings, zero warnings.
- U2: `bash scripts/tp-mongo-recon-u2.sh` (worktree `--u2` @ fda036c6). Harness output:
  `recon PASS: unit=U2 mode=live mapping=1.0 tolerances=1.0` → **PASS, rc=0**.
  Evidence: `wave1_evidence/U2_gate_recheck/`. 2 count checks (invoice_feed roots
  18,750; embedded lines 149,963), 8 per-field aggregates, 168,713 keyed diffs — zero
  findings, zero warnings.

Contract-version note (not drift): my brief cited contracts v1.0, but the run branch
carries the user-APPROVED U1 amendment (05_decisions.md 2026-09-01): mapping spec v1.1 +
canonicalization v1.1 (`null_missing_equiv` on 19 NULL-bearing numeric CUSTOMER_MASTER
columns, Tier-2 aggregate deferral only; data contract unchanged — source NULL → explicit
BSON null). U1's gate correctly runs under v1.1. U2 branched before the amendment and its
committed canonicalization is v1.0; the amendment touches only CUSTOMER_MASTER fields, so
U2's gate semantics are identical under either version. No tolerance was adjusted by this
session. No mismatch occurred, so no source double-read triage was required (source reads
were nonetheless repeated across gate + probes + replay with stable results throughout).

## 2. Adversarial probes (evidence: `wave1_evidence/probe_wave1.{py,out.json}`)

- Counts: src CUSTOMER_MASTER 25,000 = customers 25,000; src CUSTOMER_MASTER_HIST 0 =
  customer_master_hist 0 (collection exists, empty — correct empty-collection behavior);
  src INVOICE_HEADER 18,750 = invoice_feed 18,750; src INVOICE_LINE 150,000 = 149,963
  embedded + 37 orphans; src EAV(ENTITY_TYPE='CUSTOMER') 8,333 = 8,333 embedded attributes.
- Quarantine: `ow_tp_mongodb_032752_quarantine` contains exactly
  `invoice_feed_orphan_lines` with 37 docs; the orphan LINE_ID **sets** are identical to
  the 37 source INVOICE_LINE rows with no INVOICE_HEADER parent (set-compare, not just count).
- Duplicate keys: 0 dup CUST_ID / HIST_ID / INVOICE_ID / LINE_ID at source; 0 duplicate
  `lines.line_id` across all embedded arrays in target.
- Embed-array length distribution vs source child-row distribution: **exact histogram
  match** for both `invoice_feed.lines` (24 buckets 0..23, incl. 5 zero-line invoices and
  the single 23-line max invoice) and `customers.attributes` (0..5; 17,925 customers with
  zero attributes preserved as empty arrays).
- Null/missing per field: for all 17 probed customers fields — including the 19-column
  v1.1 amendment set (sub_status_cd 8,344 NULLs; territory_cd/channel_cd/rate_class_cd/
  phone3_type_cd/phone4_type_cd/ltd_billed_amt/ytd_paid_amt/udf_amt_* all-NULL 25,000;
  credit_limit_amt 5,039; related_acct_ids 4,984) — target explicit-null counts equal
  source NULL counts and target missing-field count is 0 everywhere. NULL ≠ missing
  preserved exactly as the amendment promises. Same for all 8 invoice_feed root fields (0
  NULLs both sides).
- Min/max boundary docs: customers min/max `_id` and invoice_feed min/max `_id` verified
  field-by-field doc-level (154 mapped customer fields; 8 root + 18×N line fields incl.
  line-by-line diff in line_id order) — zero diffs.
- Aggregate-only fields, doc-level spot checks: 25 random customers ×
  {cur_bal_amt, past_due_amt, ytd_billed_amt, credit_limit_amt} — exact Decimal128 match.
  50 random invoices: TOTAL_AMT exact, and Σ(embedded lines.amount) equals Oracle
  Σ(INVOICE_LINE.AMOUNT) exactly (an initial probe-side "mismatch" was my own
  float-fetch artifact; re-run with TO_CHAR-exact fetch → 0 mismatches).
- Schema shape: customers field universe contains nothing beyond the 154 mapped fields +
  `_id` + `attributes` + `ns`; `ns:"mongo_032752"` correct on 100% of docs in all three
  collections; target db contains exactly the 7 wave-0/1 collections, nothing stray.
- Indexes: customers has `tenant_id_1`, `conversion_batch_no_1`; invoice_feed has
  `cust_id_1`, `batch_no_1` (supports the RPT-114 batch-scoped reports);
  customer_master_hist `_id_` only (fine for an empty history collection).

## 3. Cross-unit consistency (shared references)

- `invoice_feed.cust_id` → `customers._id`: 0 unmatched in target, exactly matching 0
  unmatched at source.
- `customers.status_cd` distinct {1,2,3,99}, `cust_type_cd` {1,2,3}, phone type codes,
  and `invoice_feed.status_cd` {20,30,40} are all 100% decodable via wave-0 `codes`
  (`CUST_STATUS#`, `CUST_TYPE#`, `PHONE_TYPE#`, `INV_STATUS#`); distinct sets identical
  Oracle vs Mongo.
- `customers.tenant_id` / `invoice_feed.tenant_id`: **none** join to `tenants._id` — on
  either stack. This is a pre-existing source characteristic of the fixture's horror
  schema (all 25,000 CUSTOMER_MASTER.TENANT_ID values also fail the join in Oracle; 50
  distinct tenant_id values, sets identical source vs target). Parity is exact; recorded
  as an estate observation, not a defect, and nothing was "fixed".

## 4. App-level query replay (evidence: `wave1_evidence/replay_wave1.{py,out.json}`)

Replayed the wave's representative RPT-114 operations myself, importing each unit's own
`reports.py` (U1 balances pipeline, U2 status/line pipelines) and running the legacy SQL
verbatim against Oracle, at the fixture's real conversion batch 85559852:

| Operation | Oracle | Mongo | Parity |
|---|---|---|---|
| RPT-114 status rollup (STATUS_SQL vs U2 `status_pipeline`) | 3 rows (issued 5,504/55,450,955.92; overdue 2,748/27,585,416.69; paid 10,498/104,582,085.97) | 3 rows | EQUAL (counts + FM-formatted totals) |
| RPT-114 line rollup (LINE_SQL vs U2 `line_pipeline`) | 12 rows | 12 rows | EQUAL incl. line_count, amount, tax, invoices_touched |
| Balances (BALANCES_SQL vs U1 `balances_pipeline`) | 25,000 / 39,799,450.31 / 7,330,214.66 | same | EQUAL |
| Customer point lookup ×20 (cust_no + tenant_id → _id, cust_name_upper) | 20 | 20 | 0 failures |
| Same three rollups at a non-seeded batch (`ns_batch_no("mongo_032752")`=17,938,349) | 0 rows | 0 rows | EQUAL (empty-result behavior identical) |

Observation (informational): `ns_batch_no("mongo_032752")` ≠ the fixture's seeded batch
85559852 — the fixture was seeded under a different namespace string. Both stacks agree
at both batch values, so app parity is unaffected; flagging only so nobody mistakes an
empty report at the derived batch for data loss.

## 5. Per-unit cost line

| Unit | Independent recon cost (this session) |
|---|---|
| U1 | 1 live gate re-run (33,647 checks, ~3.5 min wall) + probe share (nulls×17, boundaries×2, spots×25, embed histogram) + balances/point-lookup replay; serial single live window; no writes to source or target. |
| U2 | 1 live gate re-run (168,723 checks, ~4 min wall) + probe share (orphan set-diff, line histogram, boundaries×2, spots×50 with 1 self-inflicted re-verify) + status/line rollup replay; serial single live window; no writes to source or target. |

Session total ≈ 35 min wall incl. container restart and environment reuse (wave-0 recon venv).

## 6. Findings summary

1. Zero data defects, zero code defects, zero tolerance issues found in U1 or U2. Both
   gates PASS live with 0 findings and 0 warnings; no drift to triage.
2. U1 runs under the approved v1.1 mapping/canonicalization amendment (Tier-2 aggregate
   deferral for 19 NULL-bearing numeric columns); probes confirmed the underlying data
   contract (explicit BSON null, never missing) holds at 100%.
3. Estate observations (no action): (a) fixture tenant_id values in CUSTOMER_MASTER /
   INVOICE_HEADER don't join TENANTS on either stack — pre-existing, parity exact;
   (b) `ns_batch_no("mongo_032752")` differs from the fixture's seeded batch 85559852.
4. Fixture container restarted (was stopped), never reseeded or modified, left running.

---

# Wave 1 close brief (one page)

**Wave:** 1 (U1 customers: `ow.customers` + `ow.customer_master_hist`; U2 invoice-feed:
`ow.invoice_feed` + `owq.invoice_feed_orphan_lines`).
**Independent verdict: PASS — both units; safe to open Wave 2.**

- Both unit gates were re-run VERBATIM in LIVE mode on the canonical Oracle fixture from
  each unit's own branch: U1 33,647/33,647 checks PASS (mapping v1.1, the approved
  aggregate-semantics amendment), U2 168,723/168,723 checks PASS (mapping v1.0 — U2
  branched before the amendment, which only touches CUSTOMER_MASTER, so no semantic gap).
  No mismatches, hence no drift-vs-defect triage needed.
- Adversarial probing beyond the gates found nothing: exact embed-array histograms
  (lines 0..23, attributes 0..5), exact orphan-line quarantine set (37 = 37, by LINE_ID),
  NULL→explicit-null preserved on all probed fields including the 17 all-NULL amendment
  columns, boundary docs exact at doc level, decimal spot checks exact, no stray fields
  or collections, empty `customer_master_hist` handled correctly.
- Cross-unit references are healthy where the source is healthy (invoice→customer 100%,
  all status/type codes decodable via wave-0 `codes`); the tenant_id non-join is a
  faithful copy of the source's own horror-schema state on both stacks.
- App-level RPT-114 replay (status rollup, line rollup, balances, 20 point lookups, plus
  empty-batch behavior) shows exact result parity between the legacy SQL and each unit's
  Mongo pipelines.
- Risks carried forward: none new. Secondary indexes now exist for the batch-scoped
  reports; Wave 2+ units should continue creating the ones their contracts assign.
- Nothing routed back to the orchestrator; no fixes, tolerance changes, or legacy edits
  were made by this session.
