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
