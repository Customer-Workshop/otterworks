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

## Wave 4 — `silver_dunning`, closed

| Unit | Status | PR | Evidence |
|---|---|---|---|
| `silver_dunning` | `MERGED` | #1374 | 42/42 checks, `run_mode: live`, `oracle_source_sha 0d326cad…f0d55`, seed `NS=demo SCALE=demo`. One job, two tasks over one overdue snapshot (`schedule_dunning` writes it, `suspend_overdue` verifies its sha256/`ns`/`as_of`/`batch_id`/row count and sweeps exactly it). `loaded + quarantined == source` on all four declared populations (`dunning_attempts`, `tenants`, `notifications`, `subscriptions_swept`), each with its own numerator/denominator and its own 5% evaluation; money exact to the cent (`322.58` overdue total). Measured, not assumed: `as_of` day-of-week `SAT` with a 2-day weekend shift from the source's English `DY` abbreviations, 2 candidate tenants → 1 swept / 1 skipped non-active, 1 subscription suspended with `suspended_on = 2026-02-28`, 1 notification a different `as_of` would add vs. 0 on a same-`as_of` rerun, and the unlocked-`MAX` collision exposure. All five `DUNNING-00x` transcripts reproduced individually; halt fires live in `ns=dunning_halt` with the ledger already written; append/no-op/refusal evidence in `ns=dunning_edge` only — nothing wrote a second `as_of` into `ns=demo` or into `ns=plans_edge`. |

Six defects found in review and re-proven live:

1. **Attempt numbering read the bronze ingest population only**, so every later night recomputed
   `attempt_no = 1` and the deterministic `f_md5_uuid(invoice_id || attempt_no)` id merged over the
   previous night's row — dunning escalation would have been frozen at first notice forever while the
   run reported green. The basis is now the ingest population plus this unit's own rows at
   `as_of <` this run's `as_of`, which appends `n+1` on a later night and keeps a same-night rerun a
   true no-op.
2. **Quarantine ledger identity omitted `_batch_id`**, so a later batch overwrote an earlier batch's
   record of the same rejection; and **duplicate physical rejects could collapse** into one ledger row.
   Identity is batch-scoped now and repeated rejects carry occurrence ordinals, with every rejected
   payload persisted.
3. **The 5% halt compared the *rounded* rate**, so 5.004% displayed and passed as 5.0. Both
   `rate_pct_unrounded` and `rate_pct` are kept, the comparison is exact, and the boundary case is
   proven.
4. **An `INT_MAX` attempt basis was cast to `INT` before judgment**, bypassing the overflow
   quarantine — the candidate is judged in BIGINT before any cast.
5. **An out-of-order backfill would have overwritten a later night's attempt.** Decided at parent
   level rather than by the unit: the run is **refused** (`STOPA-DUNNING-BACKFILL`) before the overdue
   snapshot is persisted and before any `MERGE`, naming the requested `as_of` and the later ones
   already present. `05_pkg_dunning.sql:43-44` puts no `p_as_of` predicate on the `MAX`, so Oracle run
   out of order appends by execution order — and a rerun of the *later* night would then append again
   on unchanged input, so matching the source literally trades one silent wrong answer for another.
   Recorded as `DIV-BACKFILL-REFUSED`; proven live (later night writes → earlier night refused with no
   target Delta version moved and no snapshot written → later-night rerun still a no-op).

### Carried out of wave 4

- **This port cannot backfill an earlier night without an operator decision.** `JOB_NIGHTLY_DUNNING`
  only ever moves forward, so the nightly path is unaffected, but an operator re-running an earlier
  `as_of` must choose renumber-by-date or append-by-execution-order explicitly.
- **D-30 held under a real writer.** The shared write on `ow_tp.silver.subscriptions` is one
  matched-only `MERGE` on `(id, ns)` touching `status_cd`/`suspended_on`: 0 inserts, 0 deletes, 0 DDL,
  0 rows with a changed non-owned column, with each updated row's prior status recorded. The
  interleaving noted out of wave 3 — a later `silver_plans` rerun reasserting the source's close-out
  over dunning's columns — is still declared-unexercised and belongs to a pre-cutover run-order
  decision, not to either unit.
- **The contract's `ANOM-NOTIFICATION-SIDE-EFFECT` description is wrong and was left untouched.** The
  source's INSERT carries a `NOT EXISTS (tenant, kind 3, sent_at = TRUNC(p_as_of))` guard, so a
  same-`as_of` legacy rerun does *not* duplicate; a different `as_of` does add a second notification
  for an already-suspended tenant. The report says so; `docs/tech-partnerships/contracts/silver_dunning.json`
  is unchanged.
- **Neither procedure was executed against Oracle** (they mutate `DUNNING_ATTEMPTS`, `TENANTS`,
  `SUBSCRIPTIONS`, `NOTIFICATIONS`): expected end state is Oracle's own evaluation of read-only
  re-expressions of the same predicates, so control flow that lives only in PL/SQL is modelled, not
  observed. Stays in `unverified_paths`, with the concurrent-collision reproduction.

## Wave 5 — `gold_finance`, closed

Merged into the run branch as PR #1382 (62/62 live recon checks, CI 5/5, all review threads judged and
resolved). The last unit, and the only one whose source of truth is not PL/SQL: `finance_excel_report.pl`
plus the `CBCUST01` fixed-width parser that feeds it. The legacy report was **executed**
(`scripts/tp-run-deterministic.sh`) and its CSV compared line-for-line against the target's export,
so parity here is measured against the source's own output rather than against a re-expression of it.

Population, which decides every figure the unit publishes: gold reads the **denormalised** CUSTBILL
stream (`ow_tp.bronze.custbill_records`), because that is what the Perl report reads. The normalised
`ow_tp.silver.invoices` figures are published beside it as the declared disagreement recorded out of
wave 1 (18,750 header rows / 1.86B against 3 normalised invoices / 375.62 in the source) — not
reconciled, not averaged, not filtered. That closes the wave-1 question of which side gold reads.

### Defects found in review and fixed before merge

1. **The evidence harness dropped the three shared gold tables** to stage a cold load, which erases
   every *other* namespace's published report and quarantine history. Replaced by `ns`- and
   `_origin`-scoped `DELETE`, with a before/after row count **and content checksum** of the rows the
   unit may not touch.
2. **Those isolation fingerprints then proved nothing**: the checksum summed `xxhash64` in `BIGINT`,
   which overflows under ANSI mode, and the resulting error was swallowed by the same handler that
   reports an absent table — so all six checks read `"table does not exist"` before *and* after.
   Existence now comes from `information_schema`, the sum is `DECIMAL(38,0)`, any other error raises,
   and every scratch cleanup runs **after** `ns=demo` is published and additionally fingerprints
   demo's own rows (66 monthly + 8 export rows byte-identical across all six).
3. **An empty population would have retracted a published report.** Both published targets carry a
   scoped `NOT MATCHED BY SOURCE ... DELETE`, so a failed CUSTBILL ingest or a wrong `ns` parameter
   would delete every published finance row for that namespace and overwrite the export with a
   header-only CSV. The legacy chain never retracts a report it wrote — it writes a new dated file.
   Refused before either publishing `MERGE` (`STOPA-RETRACTION`), naming the rows it would have
   deleted; a genuinely empty *first* load stays legal.
4. **The delete path had never removed a row in evidence** (all three checks read 0), so it could not
   be distinguished from a broken one. Both directions are now exercised live on a per-run generated
   namespace: batch 2 un-publishes one group from a still-large population, batch 3 empties it and is
   refused.
5. **The pipe-in-a-fixed-width-field population was asserted impossible rather than measured.** Nothing
   in `CBCUST01` or the parser excludes the byte the report uses as its group delimiter, so a `'U|D'`
   currency makes the legacy report print a currency and a record type no record holds. Measured live
   (`DELIMITER-IN-FIXED-WIDTH`) and declared as a divergence: the target reads the true copybook
   positions and does not reproduce the field shifting.
6. **The report used a top-level `result` key**, so the estate rollup read its `recon_result` as `None`
   — green unit, unreadable estate. Fixed in the unit; the rollup now also fails on a *named* unit with
   no report at all (`--require-units`), because absence was previously indistinguishable from success.

### Carried out of wave 5

- **D-32 is the dictionary entry this wave forced.** Devin Review read the scoped delete as a D-28
  breach; the parent review read its *absence* as publishing a total no source artifact produces. Both
  are right about entity tables and rendering targets respectively, so the boundary is now written down
  rather than left as a per-unit judgement: a derived-aggregate rendering target may un-publish a group
  its current **non-empty** population no longer contains, under four stated conditions, and no unit may
  extend that to a table publishing entities or self-declare into the carve-out.
- **The estate has no month filter and never did.** `finance_excel_report.pl` is "monthly" by file-name
  convention only; `period_month` comes from each record's own `BILL-DATE` and summing the periods
  reproduces the legacy cumulative total. A consumer expecting a month-scoped report is expecting
  something the source never produced.
- **`ANOM-PERL-ROUNDING` is real but does not bite `ns=demo`**: the float accumulator and the
  `DECIMAL(14,2)` total print the same cents on the demo population, so it is exercised on a declared
  generated namespace where they differ by one cent. The float figure stays evidence; T1 is not widened.
- **The job is declared untriggered**, like every unit job in this estate: invocation is parent-owned
  (STOP C/E). A cron window here would also be a period predicate the source does not have.
- **Wave 1's generated pipe-bearing bronze rows in an abandoned `ns` cannot be removed by this unit** —
  bronze is read-only to gold. Its own gold slices were cleaned; the bronze rows stay in
  `unverified_paths` for the ingest owner.

## Estate-wide reconciliation rollup (parent-owned)

Run from the merged run branch with wave 5 in place, over every `*.recon.json` in the tree:
`docs/tech-partnerships/recon/estate_rollup.json`.

```
bronze_core        live   green  checks=52   unverified=6
bronze_hist        live   green  checks=31   unverified=5
bronze_wide        live   green  checks=111  unverified=7
bronze_custbill    live   green  checks=10   unverified=3
silver_rating      live   green  checks=46   unverified=12
silver_invoicing   live   green  checks=69   unverified=14
silver_plans       live   pass   checks=38   unverified=9
silver_dunning     live   pass   checks=42   unverified=11
gold_finance       live   pass   checks=62   unverified=7
9 unit reports; problems: 0   (461 checks, 74 unverified paths, all run_mode=live)
```

All nine required units are named to the rollup explicitly (`--require-units`), so a unit with no
report is a reported problem rather than a pass by omission — the failure mode that a bare directory
scan cannot distinguish from success. Every unit's `unverified_paths` is carried forward unmerged and
unsummarised (74 in total): the estate is green on what it measured, and the list of what it did not
measure is part of the result, not a footnote to it.

The two estate-level gaps that no unit can close, both carried into STOP E:

- **The consumer population is unmapped** (STOP A: no audit observation window). `V$SQL`, ASH and
  `UNIFIED_AUDIT_TRAIL` are readable now, but nothing was sampled, so no evidence about real readers
  exists and none will be collected before cutover.
- **`_HIST` volume and shape are unknown.** `bronze_hist` is green against 478 history rows it
  generated on its own fixture, because the loader leaves both `_HIST` tables empty. The pipeline is
  proven; the migration is not sized.
