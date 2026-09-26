# Evidence pack check (playbook 5 step 2) — DRAFT, incomplete by construction

Run branch `tp-run/mongodb-20260926T164803Z-rt-offline`. Connectivity `offline`:
`source_access=ddl_only`, `target_access=local` (`08_connectivity.json`). Playbook 5 "Before
you start": *fixture or local-target evidence never satisfies STOP C; draft the STOP C message,
name the missing customer run, and stop.* This pack records what exists and what is missing.

| Required item | Present? | Where | Note |
|---|---|---|---|
| Coverage table | yes | `09_coverage.md` | 19 tables -> 18 unit + 1 shared, 0 unused |
| Approved mapping spec version | yes | `03_mapping_spec.json` **map-draft-3.1** (D-018/D-018a); STOP B approved map-draft-2, scoped-embed change human-approved | 16 collections, 3 derived embeds, 0 unresolved |
| Tolerances | yes | `02_tolerances.json` **tol-2** (D-011, human-approved) | exact; sample 1000 (late "2000" request declined at STOP B) |
| Every wave report | yes | `waves/wave-{0,1,2,3}.result.json` + `.brief.md`; independent recon `recon/wave-0/`, `recon/wave-3/`; waves 1-2 verifier NOT RUN (workflow reported `verifier: NOT RUN`) | all `auto_merge: false`; 0 of 12 units merge-eligible |
| Parallel-run log | **no** | — | no parallel run possible without a live source/target; no decision row skips it — it is a STOP C input the customer must supply or waive |
| Watermark recon | **no** | — | requires the customer in-network live/snapshot run (D4-1, D4-2) |
| Open-issues list with dispositions | yes | `cutover/open_issues.md` | |
| Dependency register, D1-D3 DONE or deferred with owner | partial | `07_dependency_register.md` | every D1-D3 row DECIDED with an owner; none DONE (nothing merged/repointed); D4-3 still FOUND |
| Business-logic track | partial | `cutover/runbook.md` §0 | every PL/SQL object passed Tier 4 **fixture/local only**; runbook §0 states no path may repoint until the customer run exists |
| Merge-grade recon (`live`/`snapshot`, migration cluster, `merge_eligible=true`) | **no** | — | none exists for any unit |

## Unit evidence index (all `--mode fixture --target-class local`, `merge_eligible=false`)

| Unit | Wave | Gate | Quarantine | PR (open, unmerged) |
|---|---|---|---|---|
| u-00-codes | 0 | PASS T1 1/T3 32; verifier PASS | 0 | #1708 |
| u-01-tenancy | 1 | PASS | 0 | #1712 |
| u-02-customers | 1 | T1/T2 PASS, T3 13/33,338 diffs = 13 quarantined malformed CSV (`harness_gap_csv_unparseable`) | 63 | #1716 (+ contract #1710) |
| u-03-invoicing-core | 1 | PASS | 0 | #1711 |
| u-04-usage-audit | 2 | PASS (BILLING_AUDIT_LOG 0 rows: unverified path) | 0 | #1722 |
| u-05-dunning-data | 2 | PASS | 0 | #1721 |
| u-06-invoice-header-bulk | 2 | PASS all tiers under map-draft-3.1 (168,713 keyed) | 37 orphan_line | #1724 |
| u-07-plsql-util | 3 | PASS; verifier PASS (F1 low) | 0 | #1725 |
| u-08-plsql-plans | 3 | PASS; verifier PASS | 0 | #1725 |
| u-09-plsql-rating | 3 | PASS; verifier PASS | 0 | #1726 |
| u-10-plsql-invoicing | 3 | PASS; verifier PASS | 0 | #1726 |
| u-11-plsql-dunning | 3 | PASS; verifier PASS (F2 low) | 0 | #1726 |

## Verdict
Evidence pack **INCOMPLETE** for STOP C: no parallel-run log, no watermark recon, no
live/snapshot evidence, nothing merged. Missing customer run: harness `--mode live|snapshot
--target-class migration-cluster` for u-00..u-11 by the customer DBA in-network (D4-1, D4-2),
plus production counts (D4-3) and reader confirmation (D2-4).
