# Independent cutover audit — OW_BILLING Oracle → MongoDB Atlas

- **Auditor:** independent Devin session; performed no migration work in this engagement.
- **Date (UTC):** 2026-09-01
- **Run branch under audit:** `tp-run/mongodb-20260901T032752Z` @ `74f66069`
- **Audit branch:** `recon/cutover-audit-20260901` (cut from the run branch; no commits to the run branch, no PR)
- **Source:** Oracle fixture container `otterworks-oracle-billing-oracle-billing-1`, `localhost:52521/FREEPDB1`, schema `OW_BILLING` — READ-ONLY throughout (this session provisioned its own fixture instance via `make oracle-billing-up` + `make oracle-billing-seed NS=demo SCALE=demo` and issued only `SELECT`s against it).
- **Target:** Atlas `ow_tp_mongodb_032752` (+ `_quarantine`) via secret `MONGODB_ATLAS_URI` (name only) — READ-ONLY throughout (counts, aggregations, `find_one`; no writes, no index/DDL, no other database touched).
- **Harness:** `mongo-recon-harness` v0.2.0, `pip install -e 'harness[all]'`; `recon selftest` PASS (9 canonicalization rules).

## Verdict: **COUNTERSIGNED**

The evidence pack is complete and internally consistent; four independently re-run gates
(including U0 and the two largest-volume units) reproduce the recorded verdicts
check-for-check; three independent probes reproduce the recorded population figures
exactly. The only non-PASS raw verdict anywhere in the pack is the approved U0
`fixture_meta.INITIALIZED_AT` count-only amendment, which this audit reproduced in exactly
the declared shape and no other. No findings. Two non-blocking observations are recorded
in §5.

---

## 1. Evidence-pack completeness and version consistency

| Requirement | Result |
|---|---|
| Gate `result.json` with a verdict for every unit U0–U7 | PRESENT — U0 PASS, U1 PASS, U2 PASS, U3 PASS, U4 PASS, U5 PASS, U6 PASS, U7 PASS (all `mode: live`, `tolerance_version: 1.0`, `seed: 0`) |
| Wave report for every wave 0 / 1 / 2 / 3a / 3b | PRESENT — `wave_reports/wave{0,1,2,3a,3b}.md`, each with per-unit gate re-check artifacts, adversarial probes and app-level replay evidence alongside |
| Watermark recon covers all 8 units | PRESENT — `cutover_watermark/U0..U7/result.json` plus `watermark.json` (SCN 3244576, systimestamp 2026-09-01T18:00:10Z, 20 table row counts) |
| Parallel-run log shows 3 consecutive green cycles | PRESENT — `parallel_run/log.md`, cycles 1/2/3, 8 units each, all PASS except the approved U0 DRIFT-EXPLAINED in each cycle |

**Version consistency.** Current pinned artifacts: mapping spec `1.2`, tolerances `1.0`,
canonicalization `1.2`. Each unit gate cites the mapping version in force when it ran, and
the progression matches the `05_decisions.md` amendment trail exactly:

- v1.0 (STOP B approved) → U0 (1.0), U2 (1.0)
- v1.1 (U1 halt: 19 NULL-bearing numeric `CUSTOMER_MASTER` columns get `null_missing_equiv`; canonicalization 1.0→1.1) → U1 (1.1), U4 (1.1), U7 (1.1)
- v1.2 (U3 halt: `SUBSCRIPTIONS.ENDS_ON` / `SUSPENDED_ON` get `null_missing_equiv`; canonicalization 1.1→1.2) → U3 (1.2), U5 (1.2), U6 (1.2)

Every unit that ran before an amendment was re-verified under the current spec by the
watermark recon and the three parallel-run cycles, so no unit's evidence rests solely on a
superseded spec version.

**Amendment blast radius verified.** Regenerating every re-run unit's mapping from the
current v1.2 spec (`scripts/tp_mongo/unit_mapping.py`, same invocation as the recorded
scripts) produces content byte-identical to the committed `U*/mapping/u*.json` apart from
the `version` stamp and an empty `_recon_embed_exclusions` key — i.e. the v1.1/v1.2
amendments changed nothing in the U0/U2 mappings that graded at v1.0.

`null_missing_equiv` appears in the v1.2 spec on exactly 21 fields and nowhere else:
19 `customers` fields (`channel_cd`, `credit_limit_amt`, `ltd_billed_amt`,
`phone3_type_cd`, `phone4_type_cd`, `rate_class_cd`, `sub_status_cd`, `territory_cd`,
`udf_amt_01..10`, `ytd_paid_amt`) and 2 `subscriptions` fields (`ends_on`,
`suspended_on`) — matching the approved Tier-2 deferrals with no scope creep.
`fixture_meta` is the only collection with `parity: count_only`.

**Source watermark reproduced.** All 20 recorded `watermark.json` table row counts
reproduce exactly on this session's independently seeded fixture
(`probes/source_rowcounts.json`, `all_match: true`), including `CUSTOMER_MASTER` 25,000,
`INVOICE_HEADER` 18,750, `INVOICE_LINE` 150,000, `ENTITY_ATTR_VALUE` 8,333.

## 2. Independent gate re-runs (live, serial, `--source-concurrency 1`)

Run from spec via the recorded scripts `scripts/tp-mongo-recon-u{0,1,2,3,5}.sh` with the
output directory redirected to `.migration/recon/audit/rerun/U*/` so no recorded artifact
was overwritten. Mapping regenerated from `.migration/03_mapping_spec.json` (v1.2),
tolerances `.migration/02_tolerances.json` (v1.0), canonicalization
`.migration/recon_canonicalization.json` (v1.2), `--mode live`, `--seed 0`.

| Unit | Scope | Audit re-run | Checks | Findings | Recorded gate | Recorded watermark | Match |
|---|---|---|---|---|---|---|---|
| U0 | codes / tenants / plans / fixture_meta | FAIL (raw) → **DRIFT-EXPLAINED** | 122 | 2 (`fixture_meta` only) | PASS (121) | FAIL → DRIFT-EXPLAINED (122) | YES |
| U1 (XL) | customers 25,000 + `attributes[]` 8,333 embed, customer_master_hist | **PASS** | 33,647 | 0 | PASS (33,647) | PASS (33,647) | YES |
| U2 (XL) | invoice_feed 18,750 + `lines[]` 149,963 embed | **PASS** | 168,723 | 0 | PASS (168,723) | PASS (168,723) | YES |
| U3 | subscriptions 69, subscriptions_hist 0 | **PASS** | 86 | 0 | PASS (86) | PASS (86) | YES |
| U5 (XL unit) | invoices 3 + `lines[]` 2 embed, credit_notes 5 | **PASS** | 24 | 0 | PASS (24) | PASS (24) | YES |

Tier-by-tier stats (populations, diff modes, `embeds_graded`, `deferred_to_tier3` field
lists) are identical to the recorded artifacts for all five units. U1 and U2 ran full
keyed diffs (not stratified samples) at 25,000 and 18,750 roots with all 8,333 / 149,963
embedded elements value-graded; no `UNGRADED` warning appears in any re-run.

The U0 raw FAIL is the approved deviation and nothing else: Tier 1 (4/4) and Tier 2 (12/12)
green, Tier 3 carrying exactly one `missing_doc` / `extra_doc` pair on `fixture_meta`
(`key=2026-09-01 18:13:46.073` source vs `key=2026-09-01 17:06:08.675` target) — the
instance-local `SYSTIMESTAMP` written at fixture init, declared unexercised with
count-only parity (which holds, 1 = 1) under the 2026-09-01 amendment. Because this
session seeded its own fixture instance, the timestamps differ from those in the recorded
wave-0 and watermark artifacts while the finding shape is identical, which is exactly what
the drift explanation predicts. No other collection produced a finding.

Audit artifacts: `.migration/recon/audit/rerun/U{0,1,2,3,5}/{result.json,report.md,recon.summary.md}`.

## 3. Independent probes

Executed by `probes/audit_probes.py` (output `probes/audit_probes.out.json`), written from
the ledger figures alone, not from the migration loaders.

| Probe | Expected (recorded) | Observed | Result |
|---|---|---|---|
| Orphan quarantine population | 37 in `owq.invoice_feed_orphan_lines` | 37 quarantined docs; 37 orphan rows in source (`INVOICE_LINE` with no parent `INVOICE_HEADER`) | MATCH |
| Line conservation | embedded + quarantined = 150,000 source `INVOICE_LINE` | 149,963 + 37 = 150,000 = source 150,000 | MATCH (no silent drops) |
| Subscriptions | 69 | target 69 = source `SUBSCRIPTIONS` 69 | MATCH |
| Customers + EAV embed (extra) | 25,000 roots, 8,333 attributes | 25,000 = source; 8,333 embedded = source `ENTITY_ATTR_VALUE` 8,333 | MATCH |
| Write-scope containment (extra) | 16 collections in `ow`, 1 in `owq`, `ns` stamp on every doc | exactly the 16 mapped collections; only `invoice_feed_orphan_lines` in quarantine; 0 `invoice_feed` docs missing the `ns: "mongo_032752"` stamp | MATCH |

Quarantine documents retain the source key and provenance (`line_id`, `invoice_no`,
`tenant_id`, `reason_class`, `source`, `src_system`, `quarantined_at`), satisfying the
STOP A "no silent drops" requirement.

## 4. Approved deviations — verified, not flagged

1. **U0 `fixture_meta.INITIALIZED_AT` missing/extra timestamp pair** (count-only amendment,
   raw FAIL → DRIFT-EXPLAINED). Verified: spec carries `parity: count_only` for
   `fixture_meta` with `INITIALIZED_AT` declared unexercised; count parity holds; the
   audit re-run reproduces exactly one missing/extra pair on that key and no other
   finding; source-side value is stable within a fixture instance and differs only across
   instances.
2. **v1.1 / v1.2 `null_missing_equiv` Tier-2 deferrals** (19 `CUSTOMER_MASTER` fields;
   `subscriptions.ends_on` / `suspended_on`). Verified: exactly those 21 fields carry the
   rule; the deferred aggregates appear in the corresponding `deferred_to_tier3` lists and
   the fields are then graded by the Tier-3 keyed diff, which is full-population (not
   sampled) for both `customers` (25,000) and `subscriptions` (69) and returns 0 findings.
   The data contract is unchanged: source NULL → explicit BSON null.

## 5. Observations (non-blocking, no action required before STOP C)

1. **cycle1 artifacts are the watermark recon.** `parallel_run/log.md` lists cycle1 with
   `generated_at` values identical to `cutover_watermark/U*/result.json`; there is no
   `parallel_run/cycle1/` directory. The reuse is traceable by timestamp and legitimate
   (the source was frozen and idle across the whole window), but the log does not say
   where cycle1's artifacts live. A one-line pointer in the log would remove the ambiguity.
2. **Harness does not honour `parity: count_only`** — already filed as profile feedback in
   `wave_reports/wave0.md` §1. This audit independently confirms it: any fixture instance
   with a different init timestamp Tier-3-flags `fixture_meta` despite the approved
   amendment. It is a harness-profile gap, not a migration defect, and no tolerance,
   mapping, or migrated code was altered to work around it (here or, per the artifacts, in
   the run).

## 6. Findings

**None.** No data defect, no code defect, no tolerance or mapping inconsistency, and no
undeclared deviation was found. The cutover evidence pack supports STOP C.

## 7. Audit hygiene

- No commits to `tp-run/mongodb-20260901T032752Z`; no PR opened; `main`,
  `tech-partnerships`, and `tech-partnerships-solutions` untouched and never consulted.
- No migration code, loader, mapping, tolerance, canonicalization, or ledger file was
  modified. The re-runs regenerate `.migration/recon/U*/mapping/u*.json` in place as a
  side effect of the recorded scripts; those regenerated files were left uncommitted and
  are not part of this branch (their content equivalence is reported in §1).
- Zero writes to Oracle and zero writes to Atlas. The Oracle fixture instance used here is
  this session's own, left running and unmodified.
