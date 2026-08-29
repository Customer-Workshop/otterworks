# 05 — Migration progress

Status flow: `NOT_STARTED → IN_FLIGHT → PR_OPEN → RECON_GREEN → MERGED`

| Unit | Status | Owner | Evidence |
|---|---|---|---|
| `PKG_RATING` | `NOT_STARTED` | Unassigned | No child PR or recon report yet. |
| `PKG_INVOICING` | `NOT_STARTED` | Unassigned | No child PR or recon report yet. |

## Wave 0 — parent-owned foundation

| Area | Status | Owner | Evidence |
|---|---|---|---|
| Contracts | `COMPLETE` | Parent | Nine OW_BILLING Databricks contracts authored; `make tp-validate-contracts` reports `validated 9 contracts file(s) / PASS`. |
| Capability preflight | `COMPLETE` | Parent | `.migration/07_access_checklist.md` records `probes: 11, denied: 0`. |
| Shared Terraform | `COMPLETE` | Parent | `infrastructure/terraform-databricks/` shared stack landed; children add only `jobs_<unit>.tf`. |
| Dictionary | `COMPLETE` | Parent | `.migration/09_semantic_dictionary.md` is in place from PR #1358. |
| Quarantine reason codes | `COMPLETE` | Parent | `.migration/11_quarantine_codes.md`; closed code set with no `OTHER`. |
| Golden baselines | `COMPLETE` | Parent | `.migration/12_golden_baselines.md`; 24 immutable Oracle transcripts under `procs/oracle/transcripts/`, pinned by `ORACLE_SOURCE_SHA=0d326cad54d94cd64e8abb53585b37436eaad2193fdc15ba3596fbb8db3f0d55` and verified against the Oracle SQL source. |

Wave 0 has no remaining items.

## Wave 1 — bronze ingest (fan-out 4, per STOP C)

All four units are `MERGED` into `tp-run/databricks-20260828T221250Z`. Every unit ran live against
its own seeded Oracle fixture and its own `ns=demo` slice of `ow_tp.bronze`, and each report is
validated by `make tp-validate-recon`.

| Unit | Status | PR | Evidence |
|---|---|---|---|
| `bronze_custbill` | `MERGED` | #1362 | 112 source / 107 loaded / 5 quarantined (4.46%, under the 5% halt); money exact to the cent; second run 0/0/0; two whole files refused (trailer mismatch, no completed-transfer marker) reported as operator actions. |
| `bronze_hist` | `MERGED` | #1363 | 478/478, zero quarantine — against history the unit **generated** on its own fixture, because the loader leaves `CUSTOMER_MASTER_HIST`/`SUBSCRIPTIONS_HIST` empty. Proof the pipeline works, not a sizing of the customer's history; the generator refuses any non-loopback host and requires an explicit mutate-the-source opt-in. |
| `bronze_core` | `MERGED` | #1364 | Re-measured after `make oracle-billing-seed NS=demo SCALE=demo`: 1,005/1,005, zero quarantine, 52 checks pass, second run 0/0/0, `ANOM-NUMBER-UNBOUNDED` detected on 17 scale-undeclared `NUMBER` columns. |
| `bronze_wide` | `MERGED` | #1366 | 202,083 source / 202,033 loaded / 50 quarantined (0.0247%), `BAD_DATE` 39 + `DATE_INVALID` 11; 111 checks pass; `CUSTOMER_MASTER` compared at all 155 declared columns; second run 0/0/0; PII masks attached before any business row is published. |

### Findings carried into later waves

- **Money volume is not yet exercised.** `bronze_core`'s money-bearing tables sit at base
  population because the rating/invoicing batch chain was not run against the source — deliberately,
  since generated volume is not evidence about this estate. T1 money parity is therefore proven on
  small populations in bronze; wave 2 (`silver_rating`, `silver_invoicing`) is where it meets volume.
- **`ANOM-DENORM-COPIES` — closed by a parent-owned cross-unit check** (2026-08-29, measured live
  against Oracle at `SCALE=demo` and against the merged `ns=demo` targets, both units settled so
  nothing in-flight was read). The source's disagreement is enormous and entirely real:
  `INVOICE_HEADER` 18,750 rows / 187,618,458.58 and `INVOICE_LINE` 150,000 rows / 1,855,870,025.91
  against `INVOICES` 3 rows / 375.62 and `INVOICE_LINES` 2 rows / 161.29. All nine measures — row
  counts, distinct `invoice_no`, and the money sums on both sides — match source to target exactly,
  so the migration carries the disagreement faithfully rather than resolving or hiding it. Resolving
  it remains a source data-quality question and is explicitly **not** a parity question (the
  `bronze_wide` contract declares it a coverage gap); what was unproven and is now proven is that
  neither unit lost a row or a cent on either side of it. The denormalised copies are the ones a gold
  finance consumer would find first and they are ~5 orders of magnitude larger, so wave 5 must state
  which side it reads.
- **No transaction spans a unit's tables.** Each target is merged separately, so a mid-publication
  failure leaves the unit's tables at different versions until the next run converges them. Acceptable
  for bronze (`MERGE` is convergent and reruns are no-ops); a snapshot-and-pointer publication is a
  parent-owned decision if a gold consumer ever needs cross-table atomicity.
- **No dictionary gaps were reported.** All four units implemented D-01..D-25 as written and none hit
  a semantic the dictionary does not cover, so no corrections are harvested from wave 1.

## Wave 2 — pilot, closed

Both pilot units are green and merged into the run branch, in the required order.

| Unit | Status | PR | Evidence |
|---|---|---|---|
| `silver_rating` | `MERGED` | #1371 | 46/46 checks; money exact to the cent; second run a true no-op. Five money-path defects found in review and re-proven live: a re-rate `MERGE` overwriting the columns Oracle's `DUP_VAL_ON_INDEX` path deliberately leaves alone, a halt that discarded its own quarantine rows, an unreachable `NUMERIC_OVERFLOW` guard, a rollover bank read from bronze only (wrong money on a second consecutive period), and truncated subscription timestamps where Oracle does fractional-day arithmetic. |
| `silver_invoicing` | `MERGED` | #1372 | 69/69 checks; 72 invoices / 347 lines / 5 credit applications, `loaded + quarantined == source` on every owned table, quarantine 0 rows (0% of 72 invoice drivers), all six `INVOICE-00x` transcripts individually reproduced. Rating recomputed inline (`ow_tp.silver.rating_*` never read: consuming it would change 2 invoices); `0.0825` preserved with unrounded tax halves (rounding them first would change 26 invoices); sequential burn-down with the source's over-application (2 notes debited beyond their balance, 71.08 of counter carried); scoped static line rebuild replacing `EXECUTE IMMEDIATE`. |

### Pilot exit criteria (`10_wave_plan.md`)

1. **Both green and merged, each with a rerun proving idempotency** — met; second runs change zero
   rows, attributed to this run's own Delta commits by `job.jobRunId`.
2. **Quarantine rate recorded per source table and under 5%** — met: zero on both units' populations.
   That is a real result and a weak one: the quarantine *write* path for `FK_ORPHAN`, `KEY_NULL`,
   `KEY_DUPLICATE`, `CODE_UNKNOWN` and `NUMERIC_OVERFLOW` is implemented and reachable (proven
   synthetically, including the overage overflow) but exercised by no live row, so both units carry it
   as an unverified path rather than a proof. The estate's real bad-date exposure remains the 0.0247%
   `bronze_wide` measured.
3. **Money exact to the cent with quarantine counts beside every figure** — met, and this is where T1
   first met the estate's genuinely hostile arithmetic (half-cent tax halves, over-applied credit,
   `DECIMAL(38,2)` pre-cast overflow guards).
4. **Dictionary feedback harvested before wave 3 is briefed** — met: D-26 (parent row written before
   the work that can fail), D-27 (re-issue recomputes credit from its own burnt balances; target
   stays idempotent by design), D-28 (nothing in the estate retracts), D-29 (burnt-down balances have
   no target column) added to `09_semantic_dictionary.md`, plus tolerance items 5–7 in
   `03_recon_tolerances.md` fixing the quarantine-rate basis, quarantine-as-ledger scoping, and
   run-attributed idempotency evidence.

### Carried out of wave 2, unresolved by design

- **Multi-table publication atomicity** and **retraction** are both in `10_wave_plan.md` as
  estate-level decisions. Wave 3 and 4 inherit them and must not invent unit-local answers.
- **The re-issue double burn (D-27) stays undiverged-from.** A target rerun is a no-op; the source's
  second issue is not reproduced. Exposure measured at 13.92 across 2 invoices.

## Wave 3 — `silver_plans`, closed

| Unit | Status | PR | Evidence |
|---|---|---|---|
| `silver_plans` | `MERGED` | #1373 | 38/38 checks, `run_mode: live`, two declared namespaces. `ns=demo` (migrated source state) = 69 source-migrated subscriptions + the 2 transcript-pinned close-out identities and nothing else, parity 0/3 plans, 0/69 entitlements, 0/71 subscriptions, zero quarantine. `ns=plans_edge` (generated fixture, declared as such) carries the procedure evidence: `UNKNOWN` tiers 2, tied `starts_on` 1, plan absent from source 1, plan present-but-rejected 1, strict-`<` overlaps 2, cancelled visited 1, suspended→active 1, re-apply identity collision 1, plus the cold-load/no-op idempotency pair (25/79/71/5 inserted, then 0/0/0) attributed by pre-run Delta version + `job.jobRunId`. Halt bases evaluated per population: plans 3.85%, subscriptions 3.61%, entitlements 1.39% in `plans_edge`, 0% in `demo`. |

Five defects found in review and re-proven live, all of which would have passed a naive green:

1. **A fabricated plan-change batch published into `ns=demo`.** The spec derives one `sp_change_plan`
   request per covering tenant; the first revision applied all 69, closing every open subscription and
   inserting 69 synthetic ones, then reconciled Oracle's re-expression of the same invented input
   against it. `ow_tp.silver.subscriptions` is what waves 4 and 5 read next. Only the transcript-pinned
   requests are applied now; the other 67 are measured on both sides and written nowhere, with the
   resulting 69-vs-71 row asymmetry declared rather than hidden.
2. **Anomaly coverage that was listed, not exercised.** Six populations sat at zero on the demo seed,
   including three `must-detect` anomalies. They are now demonstrated non-zero on a declared generated
   fixture in a separate namespace, which never touches another unit's `ns=demo` bronze.
3. **A 5% halt that could only fire on one of three populations** (item 5 of `03_recon_tolerances.md`,
   the same defect wave 2 had) — now one paired numerator/denominator per declared population, and a
   population that is accounted but not evaluated raises.
4. **A plan the run rejected counted as Oracle's genuinely missing plan.** D-18 null extension is
   source-presence-driven; a plan present in the source but rejected by this run rejects its dependents
   as `FK_ORPHAN` instead. The two populations are now separately measured.
5. **Idempotency evidence from already-converged tables and superseded code** — replaced by a true cold
   load plus no-op rerun of the final code.

### Carried out of wave 3

- **D-30** (shared write targets are owned by *column*, not by row) and **D-31** (D-28's no-retraction
  rule covers rows the *source* published, not a unit's own synthetic job input) are now binding; the
  retraction section of `10_wave_plan.md` carries the boundary. Wave 4 must not read D-31 as licence to
  sweep rows the source issued: its driver is the source's own overdue population, so it issues no
  `DELETE` at all.
- **The `_origin` gate does not protect wave 4's write, and the record says so.** It fires only on rows
  carrying a foreign `_origin`; D-30 makes dunning's write a column-scoped update of
  `status_cd`/`suspended_on` on rows whose `_origin` `silver_plans` owns, so the gate does not skip it
  and a later `silver_plans` rerun would reassert the source's close-out over dunning's columns.
  Reconciling that is wave 4's job under D-30, and the interleaved run stays declared-unexercised until
  wave 4's writer exists.
- **`sp_change_plan` was never executed against Oracle** (it mutates `SUBSCRIPTIONS`): the parity side
  is Oracle's own evaluation of a read-only re-expression, and stays in `unverified_paths`.
