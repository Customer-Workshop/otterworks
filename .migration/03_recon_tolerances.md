# 03 — Reconciliation tolerances (THE parity contract)

**Version:** v1 (2026-08-28) · **Estate:** `OW_BILLING` (Oracle AI Database 26ai Free,
`23.26.3.0.0`, PDB `FREEPDB1`) · **Recon mode: LIVE**

Every recon report cites this file by version. A recon result without a tolerance version
is meaningless. Rows are **FACT** (explicitly confirmed by the customer) or **PROPOSED**
(default applied here, pending confirmation at STOP A).

## Recon mode

**LIVE.** Lakehouse Federation over JDBC from Databricks to Oracle is approved by the
customer, so recon recomputes from the target and compares against the live source over
federation. No snapshot baseline is required. If the JDBC path is later withdrawn, this
file must be re-versioned to DEGRADED, which brings its own evidence standard (snapshot
manifests, sample-coverage statistics, mandatory in-perimeter run before STOP E) — that is
a re-version, not a footnote.

## Tolerances by data type

| # | Data type / class | Tolerance | Status | Notes |
|---|---|---|---|---|
| T1 | Money (`NUMBER(14,2)` → `DECIMAL(14,2)`) | **Exact to the cent.** Any difference fails recon. No epsilon, no relative tolerance on totals or aggregates. | **FACT** | Forbids any double/float path through rating or invoicing, including intermediate expressions and window aggregates. A `DOUBLE` anywhere on a money lineage is a PR rejection, not a tolerance question. |
| T2 | Row counts | **Zero tolerance**, over the *same row population* (see T3 and §Quarantine). | PROPOSED | |
| T3 | String-typed dates (`VARCHAR2(9)` in `CUSTOMER_MASTER`) | Parsed values must match exactly. Unparseable values: **quarantine the row, continue the load, count it in recon.** | **FACT** | Quarantine count is recon *output*, not a warning. See §Quarantine for how this interacts with T1/T2. |
| T4 | Century window for 2-digit years | `00–49` → 2000s, `50–99` → 1900s, applied uniformly; any value outside the window quarantines under T3. | PROPOSED | Must be one decision for the whole estate, not per unit. |
| T5 | Integer / code columns (`NUMBER(4,0)`, `NUMBER(10,0)`) | Exact. | PROPOSED | |
| T6 | Oracle `NUMBER` without precision | Exact, after the dictionary pins an explicit target type per column. Recon may not run on a column whose target type is still undecided. | PROPOSED | Silent-wrong-answer class: an unpinned `NUMBER` becomes `DOUBLE` by default in most translation paths. |
| T7 | Timestamps / `DATE` columns | Exact to the second, UTC-normalised, no timezone inference. Sub-second precision: source has none; target must not invent one. | PROPOSED | |
| T8 | Strings | Exact, byte-for-byte after a single documented trim rule (trailing spaces only). Case and collation differences are failures, not tolerances. | PROPOSED | Oracle `VARCHAR2` padding is the usual source of noise here. |
| T9 | NULL vs empty string | Oracle treats `''` as NULL; the target must preserve the source's observable behaviour, and recon compares NULL-ness explicitly. | PROPOSED | `NVL`/`DECODE` translation hazard from the intake dialect table. |
| T10 | Unordered results / ties | Comparison is order-independent, on a declared key per unit. A unit with no stable key cannot be reconciled and must be escalated, not approximated. | PROPOSED | |
| T11 | Aggregates (SUM/AVG/COUNT) | Exact under T1 for money; `AVG` computed as `SUM/COUNT` on `DECIMAL`, never on floats, with the rounding step named in the unit's recon query. | PROPOSED | Engine-difference in `AVG` truncation is the classic first red wave. |
| T12 | Legacy swallowed failures (`WHEN OTHERS THEN NULL`) | The target must **not** reproduce silent swallowing. A legacy row that only exists because an error was swallowed is a defect-ledger entry, not a parity target. | PROPOSED | Recon must never credit the target for reproducing a legacy bug. |

## Quarantine interaction (T1 × T2 × T3)

Money is compared exactly, but a row can be quarantined for an unrelated bad date. A
quarantined row removes its amounts from the target population, which would surface as a
money mismatch even when every converted expression is correct. Therefore:

1. Recon compares money and row counts over the **same row population** on both sides:
   source rows minus quarantined rows.
2. Every money comparison in every recon report states the **quarantine count** alongside
   it. A recon report with money figures and no quarantine count is incomplete.
3. Quarantined rows are themselves reconciled: the quarantine table's row count plus the
   loaded row count must equal the source row count exactly.
4. **A load that quarantines every row fails loudly.** Quarantine rate above 5% of a
   unit's source rows halts the unit and escalates rather than reporting green on a small
   surviving population. (FACT (customer-confirmed 2026-08-28).)

## Recon economics

| Control | Value | Status | Rationale |
|---|---|---|---|
| Row-level diff ceiling | Units up to **200,000 source rows** get full row-level diffs. Above that, recon switches to keyed stratified sampling plus **full aggregates** (aggregates are never sampled). | PROPOSED | `INVOICE_LINE` at 150,000 rows sits under the ceiling, so the pilot runs full row-level. `CUSTOMER_MASTER` 25,000, `INVOICE_HEADER` 18,750. |
| Sampling design, above the ceiling | Keyed stratified sample, minimum 10,000 rows or 5% (whichever is larger), stratified by tenant and by month of the parsed date; sample coverage statistics reported. | PROPOSED | Sample parity never extrapolates to the whole population, and reports must say so. |
| Legacy-query concurrency cap | **3** concurrent recon queries against Oracle, independent of session fan-out width. | PROPOSED | This is a live billing database; recon load is a business decision, not a throughput knob. Fan-out width above 3 queues its recon rather than raising the cap. |
| Recon query timeout | 300s per query, then reported as `blocked` with the query text — never silently retried at a looser tolerance. | PROPOSED | |

## Amendment procedure

A tolerance changes **only** by explicit customer approval, recorded as a **new dated
version of this file with the superseded row preserved**, plus a stated re-verification
scope for waves already merged under the old tolerance. Children always read the current
version and its date; they never see an ambiguous tolerance and never negotiate one
locally. Loosening a tolerance to make a red recon pass is forbidden.

## Known coverage gap carried from intake (not a tolerance)

Consumer population is declared UNMAPPED (D4-1) and no audit-trail observation window will
be run (D4-2, risk accepted). No tolerance in this file mitigates that: recon proves the
data matches, not that every reader was found. Recon reports must not be cited as consumer
coverage evidence.
