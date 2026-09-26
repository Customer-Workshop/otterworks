# Playbook 5 step 3: independent audit (STOP C)

- Engagement: offline OW_BILLING (Oracle, PDB FREEPDB1) -> MongoDB `ow_billing_migration` (local `mongo:7`)
- Run branch audited: `tp-run/mongodb-20260926T164803Z-rt-offline` @ `7bea171d` (checked out read-only; no other branch read except the unit PR heads listed in `04_progress.md`)
- Audit branch: `tp-run/mongodb-20260926T164803Z-rt-offline--audit` (this file is the only change)
- Auditor: independent session `devin-743077ac8cb948589fadfcc1cfef0932`; migrated nothing; ran no recon, no containers, no Oracle/Mongo connection; no PR mutated
- Inputs: `5-cutover.md` (plugin 0.3.0), plugin `AGENTS.md` rules 1-11, repo `AGENTS.md`, `.migration/00..10`, `census.json`, `waves/wave-{0,1,2,3}.result.json`, `recon/wave-0/report.md`, `recon/wave-3/**`, `cutover/{runbook,evidence_pack,open_issues}.md`, per-unit `services/legacy-billing/migration/mongo/recon/<unit>/result.json` on each unit PR head (`refs/pull/<n>/head`), builtin PR status for PRs #1708-#1726, and the orchestrator session's incoming human messages (for checklist 4)

## Final verdict

**STOP C: BLOCKED.** `08_connectivity.json` records `source_access=ddl_only`, `target_access=local`, `policy=offline`. Playbook 5 step 5 and plugin rule 11 make STOP C blocking whenever either axis is `ddl_only`/`local`: only `live`/`snapshot` recon against the migration cluster is merge evidence, and none exists (no unit result is live/snapshot; every result has `merge_eligible=false`; no PR merged). The evidence pack's `INCOMPLETE` verdict is **correct and supported**. Cutover stays blocked pending the customer's in-network live/snapshot run (D4-1, D4-2) plus the remediation of the findings below.

## Checklist summary

| # | Item | Status | Basis |
|---|---|---|---|
| 1 | Coverage: census table -> unit -> result file with gate verdict | PASS (with GAP on evidence location) | 19/19 tables mapped; 12/12 units have a result.json with `verdict`; result files live on PR heads, not the run branch (F-05); wave-0 also has only `recon/wave-0/report.md` on the run branch |
| 2 | Unit results: mode/target_class/merge_eligible/tiers/quarantine | PASS | all 12 `mode=fixture`, `target_class=local`, `merge_eligible=false`; no live/snapshot claim anywhere |
| 3 | Mapping/tolerance versions | PASS with FAIL on labels | `03_mapping_spec.json`=`map-draft-3.1`, `02_tolerances.json`=`tol-2` as D-011/D-018/D-018a/D-019 require; label drift in u-07/u-08 subsets+result.json, u-04 subset, `00_context.md`, `02_tolerances.md` title (F-03, F-04) |
| 4 | Decision provenance, `user:` rows tie to human replies | PASS | 22 rows D-000..D-020 (+D-000a) all carry provenance; both `user:` approvals (D-011, D-018) and the late change request (D-002) tie to timestamped human messages |
| 5 | Dependency register D1-D3 state+owner | PASS with GAP | 11/11 D1-D3 rows have state+owner/plan; 0 are `DONE` (all `DECIDED`); D4-3 still `FOUND` |
| 6 | Evidence pack vs playbook 5 step 2 | PASS (agree INCOMPLETE) | missing: parallel-run log, watermark recon, live/snapshot wave reports, merged units, DONE dependencies |
| 7 | Runbook: executors, rollback trigger, PNR, no Devin-executable step | PASS with GAP | every production step names a customer executor; trigger and PNR stated; rollback untested, `--watermark` harness support unverified (F-08) |
| 8 | PR state | PASS | 10/10 PRs `open`, unmerged, base = run branch (table below) |
| 9 | STOP C must be blocked | PASS (BLOCKED) | see verdict |

## Findings

| ID | Severity | Item | Finding | Evidence |
|---|---|---|---|---|
| F-01 | BLOCKER | 9 | No live/snapshot recon evidence exists; every unit is fixture/local. STOP C cannot pass on this evidence by rule. | `08_connectivity.json` `source_access=ddl_only`, `target_access=local`; all 12 result.json `mode=fixture`, `target_class=local`, `merge_eligible=false`; `evidence_pack.md` "INCOMPLETE" |
| F-02 | BLOCKER | 5, 6 | No D1-D3 dependency is `DONE`; writers (PL/SQL packages, billing app, seeder, triggers), readers (reports, CUSTBILL extract, harness) and scheduled jobs all remain on Oracle. Playbook 5 step 2 requires every D1-D3 row DONE before STOP C. | `07_dependency_register.md` rows D1-1..D1-4, D2-1..D2-4, D3-1..D3-3 all `DECIDED`; `runbook.md` phase outcome "read-consumer cutover, not full retirement" |
| F-03 | HIGH | 3 | Version-label drift in committed evidence: `recon/u-07-plsql-util/{mapping.subset.json,result.json}` and `recon/u-08-plsql-plans/{...}` on PR #1725 carry `map-draft-2` (content is verbatim map-draft-3.1 per wave-3 verifier D1). u-04's subset on PR #1722 also reads `map-draft-2`. The committed gate evidence for u-07/u-08 therefore does not name the spec in force. Already tracked as OI-9 / wave-3 D1; not yet fixed. | `git show refs/pull/1725/head:services/legacy-billing/migration/mongo/recon/u-07-plsql-util/result.json` -> `mapping_version: map-draft-2`; same for u-08; `recon/wave-3/report.md` §Deviations D1 |
| F-04 | MEDIUM | 3 | Units u-00, u-01, u-03, u-04, u-05 were gated under `map-draft-2`/`tol-1` only; u-02 under `map-draft-2`/`tol-2`. None were re-gated under the approved `map-draft-3.1`/`tol-2` (only u-06 and u-09..u-11 were). D-018 states the 3.1 change touches only `invoiceHeader.lines`, and D-011 states tol-2 only adds quarantine-aware grading, so the wave 0-2 verdicts are plausibly unaffected, but that is a reasoned claim, not evidence. `00_context.md` still says tolerances "version `tol-1`" and `02_tolerances.md` is titled tol-1. | result.json on PR heads #1708 (`map-draft-2`/`tol-1`), #1712, #1711, #1722, #1721 (same), #1716 (`map-draft-2`/`tol-2`); `00_context.md:38`; `02_tolerances.md:1` |
| F-05 | MEDIUM | 1 | The per-unit `result.json` files requested for audit under `services/legacy-billing/migration/mongo/recon/*/` do not exist on the run branch; they exist only on the unmerged PR heads. On the run branch only `.migration/recon/wave-3/<unit>/result.json` (verifier re-runs) and `recon/wave-0/report.md` exist; waves 1-2 have no run-branch result artefacts and no independent verifier ran (`wave-1.result.json`/`wave-2.result.json` `verify: null`). Wave 1-2 evidence is single-source (child self-report). | `ls services/legacy-billing/migration/mongo/recon` -> no such directory on run branch; `evidence_pack.md` / OI-10 acknowledge the missing wave 1-2 verifier |
| F-06 | MEDIUM | 2 | u-02-customers final gate is `verdict=FAIL` (Tier 3 13 field diffs on `RELATED_ACCT_IDS->relatedAcctIds`, all `malformed_csv`), accepted as a known recon-0.3.2 `csv_to_array` limitation (D-016, OI-3). No unit result exists with a PASS verdict for u-02. Quarantine: `bad_date` 50, `malformed_csv` 13, `eav_orphan` 0 (`load_report.json`). | PR #1716 `recon/u-02-customers/result.json` tiers `[T1 pass 3, T2 pass 30, T3 FAIL 33338 checks, 13 findings]`, `load_report.json` `quarantine` |
| F-07 | MEDIUM | 2 | `BILLING_AUDIT_LOG` (u-04) and `CUSTOMER_MASTER_HIST` (u-02) and `SUBSCRIPTIONS_HIST` (u-01/u-08) have 0 fixture rows; their gates pass trivially and are unverified. Result.json for wave 0-2 units carry no quarantine field; quarantine counts are only in loader side files (`load.summary.json`, `load_report.json`). | `wave-2.result.json` finding on 0-row table; PR #1716 result.json `customerMasterHist.population: 0`; OI-4 |
| F-08 | LOW | 7 | Runbook step 2 relies on `--watermark`/`--since` incremental load semantics that no recon/loader evidence in this engagement exercised; rollback path is described but untested (playbook 5 "Done when" requires a tested rollback). No step is executable by Devin (verification queries Devin runs are read-only and post-repoint, as step 6 allows). | `cutover/runbook.md` §2 steps, §Rollback; `evidence_pack.md` "no watermark recon" |
| F-09 | LOW | 3 | Two low-severity code parity gaps found by the wave-3 verifier remain open on u-07 (`code_desc(NULL)` TypeError vs `UNKNOWN(-1)`) and u-11 (`suspend_overdue` day-granularity cutoff). Unreachable from fixture; reachable on a live source. | `recon/wave-3/report.md` F1, F2; OI-7/OI-8 |
| F-10 | LOW | 1 | `09_coverage.md` totals line is internally inconsistent ("12 unit-assigned + 1 shared = 19 (17 unit + 1 shared ...")"); the row-level assignments are correct (18 unit-assigned + 1 shared = 19). | `09_coverage.md:74`; D-004 "19 tables -> 18 unit + 1 shared" |
| F-11 | LOW | 2 | `redaction_salted=false` in every result.json (`RECON_REDACT_SALT` unset). Acceptable for the synthetic fixture; must be set before any live run (rule 8). `recon/u-06-invoice-header-bulk/load.summary.json` persists per-row `quarantine_rows` ids; harmless for fixture rows but the loader would persist live row ids if run unchanged. | wave-3 report F3; PR #1724 `load.summary.json` |
| F-12 | INFO | 4 | Process incidents recorded and corrected: D-017 (orchestrator commit on batch branch, corrected without force-push), D-000a (`allowed_targets.json` `catalogs` key for co-installed DBX hook), D-008 (fan-out env workaround). Wave-3 verifier report states it read `tech-partnerships` for the Oracle Makefile, outside the run-branch-only scope this audit was given; it did not affect evidence content. | `05_decisions.md` D-017, D-000a, D-008; `recon/wave-3/report.md` header |
| F-13 | INFO | 4 | D-002 change request ("sample size 2000") arrived 17:05:37 UTC, after the STOP A 60 s window, and was correctly not applied (recorded as pending for the next stop; STOP B D-007 kept sample 1000). | `05_decisions.md` D-002, D-007; orchestrator session incoming message 17:05:37 UTC |

## 1. Coverage

`census.json` `tables` has 19 entries. `09_coverage.md` maps each to a unit; each unit has a result.json with a `verdict` (location: PR head unless noted).

| Census table | Unit | Result file (verdict) |
|---|---|---|
| CODES | shared / u-00-codes | #1708 `recon/u-00-codes/result.json` PASS; run-branch `recon/wave-0/report.md` |
| TENANTS, PLANS, SUBSCRIPTIONS, SUBSCRIPTIONS_HIST | u-01-tenancy | #1712 PASS |
| CUSTOMER_MASTER, ENTITY_ATTR_VALUE, CUSTOMER_MASTER_HIST | u-02-customers | #1716 FAIL (13 malformed_csv, accepted D-016) |
| INVOICES, INVOICE_LINES, CREDIT_NOTES, RATING_PERIODS, RATING_RESULTS | u-03-invoicing-core | #1711 PASS |
| USAGE_EVENTS, BILLING_AUDIT_LOG | u-04-usage-audit | #1722 PASS (BILLING_AUDIT_LOG 0 rows) |
| DUNNING_ATTEMPTS, NOTIFICATIONS | u-05-dunning-data | #1721 PASS |
| INVOICE_HEADER, INVOICE_LINE | u-06-invoice-header-bulk | #1724 PASS (map-draft-3.1 rerun) |
| PL/SQL: PKG_OW_UTIL / PKG_PLANS+2 triggers / PKG_RATING / PKG_INVOICING / PKG_DUNNING+JOB_NIGHTLY_DUNNING | u-07..u-11 | #1725/#1726 PASS; run-branch `.migration/recon/wave-3/<unit>/result.json` PASS |

Excluded and justified in `09_coverage.md`: 5 sequences, 2 identity triggers, FIXTURE_META, 2 unparsed statements. JOB_PURGE_AUDIT_LOG covered by u-04 (D3-2).

## 2. Unit results (from result.json on each PR head; wave-3 verifier copies on run branch agree tier-for-tier)

| Unit | PR head | mode | target_class | merge_eligible | map / tol | Tiers (pass/checks) | verdict | Quarantine |
|---|---|---|---|---|---|---|---|---|
| u-00-codes | #1708 @0921b6d0 | fixture | local | false | map-draft-2 / tol-1 | T1 1, T2 0, T3 32 | PASS | 0 |
| u-01-tenancy | #1712 @ffb28327 | fixture | local | false | map-draft-2 / tol-1 | T1 4, T2 10, T3 143 | PASS | 0 |
| u-02-customers | #1716 @79d03651 | fixture | local | false | map-draft-2 / tol-2 | T1 3, T2 30, T3 FAIL 33338 (13 findings) | FAIL | bad_date 50, malformed_csv 13 |
| u-03-invoicing-core | #1711 @51be75c2 | fixture | local | false | map-draft-2 / tol-1 | T1 5, T2 16, T3 19 | PASS | 0 |
| u-04-usage-audit | #1722 @b3213a16 | fixture | local | false | map-draft-2 / tol-1 | T1 2, T2 4, T3 817 | PASS | 0 (audit log 0 rows) |
| u-05-dunning-data | #1721 @2eb90e54 | fixture | local | false | map-draft-2 / tol-1 | T1 2, T2 5, T3 2 | PASS | 0 |
| u-06-invoice-header-bulk | #1724 @330e5738 | fixture | local | false | map-draft-3.1 / tol-2 | T1 2, T2 2, T3 168713, T4 3 | PASS | orphan_line 37 |
| u-07-plsql-util | #1725 @6232d4e0 | fixture | local | false | map-draft-2 (label; F-03) / tol-2 | T1 2, T2 1, T3 32, T4 2 | PASS | 0 |
| u-08-plsql-plans | #1725 @6232d4e0 | fixture | local | false | map-draft-2 (label; F-03) / tol-2 | T1 4, T2 10, T3 143, T4 4 | PASS | 0 |
| u-09-plsql-rating | #1726 @468bb75b | fixture | local | false | map-draft-3.1 / tol-2 | T1 2, T2 8, T3 6, T4 2 | PASS | 0 |
| u-10-plsql-invoicing | #1726 @468bb75b | fixture | local | false | map-draft-3.1 / tol-2 | T1 5, T2 16, T3 19, T4 3 | PASS | 0 |
| u-11-plsql-dunning | #1726 @468bb75b | fixture | local | false | map-draft-3.1 / tol-2 | T1 5, T2 10, T3 142, T4 3 | PASS | 0 |

No result claims `live`/`snapshot`, `migration_cluster`, or `merge_eligible=true`. `04_progress.md` and all four `waves/wave-*.result.json` agree (`merged_prs` empty/none, `auto_merge=false`).

## 3. Mapping and tolerance versions

- `03_mapping_spec.json` `version: map-draft-3.1`: matches D-018 (map-draft-3 approved, `child_where`), D-018a (target_where corrected to `lines.lineNo`, effective label 3.1), D-019 (u-06 PASS under 3.1), `waves/wave-3.result.json` `mapping_version: map-draft-3.1`, and u-06/u-09..u-11 result.json. PASS.
- `02_tolerances.json` `version: tol-2`: matches D-011 and wave-3 `tolerance_version: tol-2`. PASS.
- Drift: see F-03 (u-07/u-08/u-04 subsets labelled `map-draft-2`), F-04 (wave 0-2 gates never re-run under 3.1/tol-2; `00_context.md:38` and `02_tolerances.md` title still `tol-1`).

## 4. Decision provenance

All 22 rows (D-000, D-000a, D-001..D-020) carry a provenance cell. Distribution: intake/orchestrator/default-accepted (STOP A D-001, STOP B D-007 under `stop_mode=soft` 60 s per `00_context.md:45`), workflow results (D-009, D-012, D-013, D-020), and three human-origin rows. Human ties (orchestrator session `devin-983733d4647d4ea2b1fd4344adfa7b65`, incoming user messages):

| Row | Provenance text | Human message |
|---|---|---|
| D-002 | late change request, not applied | 17:05:37 UTC "Change request: set sample size to 2000 ..." (after STOP A 60 s window) |
| D-011 | `user: chat reply "approve tol-2 quarantine-aware grading" (wave-1 close)` | 18:11:02 UTC "approve tol-2 quarantine-aware grading" |
| D-018 | `user: chat reply "approve map-draft-3 child_where" (wave-2 close)` | 18:31:11 UTC "approve map-draft-3 child_where. Note ... where-scoped embed makes the harness zero merge_eligible (known limitation) ..." |

No `user:` row is untied. The notification contract (`00_context.md:51`, one message per STOP/wave close/halt) is consistent with the stop sequence recorded. No customer-signed risk-accept row exists (none needed: `08_connectivity.json` `blocked=false`, both axes fell back by `policy_offline`, not by a rule-10 failure).

## 5. Dependency register

All D1-D3 rows have state + owner/plan; none `DONE`:

D1-1, D1-2, D1-3, D1-4 (writers), D2-1, D2-2, D2-3, D2-4 (readers), D3-1, D3-2, D3-3 (scheduled) = `DECIDED`. D4-1, D4-2 `DECIDED` (customer-owned access); D4-3 `FOUND` (production counts, customer DBA). See F-02.

## 6. Evidence pack vs playbook 5 step 2

| Step 2 item | Present | Note |
|---|---|---|
| Coverage | yes | `09_coverage.md` |
| Mapping version | yes | `map-draft-3.1` (label drift F-03/F-04) |
| Wave reports | partial | fixture/local only; waves 1-2 no independent verifier (F-05) |
| Parallel-run log | no | none possible offline |
| Watermark recon | no | none |
| Open issues | yes | `open_issues.md` OI-1..OI-12 |
| Dependencies DONE | no | F-02 |
| Business-logic track | partial | fixture parity replays 24/24 + probes; no live source |

Verdict: **agree, INCOMPLETE.**

## 7. Runbook

`cutover/runbook.md`: preconditions require live/snapshot PASS and merged units; every production step names a customer executor (customer DBA, customer data team, customer billing team); rollback trigger "any verification query mismatching, or a first-cycle recon FAIL, within 24 h of repoint"; point of no return "the first write repointed to MongoDB" (excluded from this phase). Devin's only role is post-repoint read-only verification queries (playbook step 6). No step is executable by Devin: no cutover principal exists in this workspace (rule 5). GAP: rollback untested, incremental `--watermark` load unexercised (F-08).

## 8. PR state (builtin PR status, read-only; no comment/approve/merge/close)

| PR | Head | State | Merged | Base |
|---|---|---|---|---|
| #1708 | `--w0-b01` | open | no | run branch |
| #1710 | `--w1-b02-contract` | open | no | run branch |
| #1711 | `--w1-b03` | open | no | run branch |
| #1712 | `--w1-b01` | open | no | run branch |
| #1716 | `--w1-b02` | open | no | run branch |
| #1721 | `--w2-b02` | open | no | run branch |
| #1722 | `--w2-b01` | open | no | run branch |
| #1724 | `--w2-b03` | open | no | run branch |
| #1725 | `--w3-b01` | open | no | run branch |
| #1726 | `--w3-b02` | open | no | run branch |

Run branch = `tp-run/mongodb-20260926T164803Z-rt-offline` for all 10. (The `gh pr view` CLI was unavailable in this session; the builtin PR viewer returned state/base/head directly.)

## 9. STOP C

BLOCKED. Required before re-audit: customer in-network `--mode live|snapshot --target-class migration_cluster` recon for all 12 units with `merge_eligible=true` (D4-1, D4-2), `RECON_REDACT_SALT` set, u-07/u-08/u-04 subsets relabelled to `map-draft-3.1`, wave 0-2 units re-gated under `map-draft-3.1`/`tol-2`, u-02 `csv_to_array` limitation resolved or risk-accepted by the customer, D1-D3 rows moved to DONE for the chosen phase, and a rollback rehearsal recorded.
