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
- **`ANOM-DENORM-COPIES` is unclosed.** The denormalised reporting copies can only be reconciled
  against the normalised invoice tables owned by `bronze_core`; both were loading concurrently, so no
  cross-unit comparison was run. It belongs to a parent-owned check now that both units are merged.
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
