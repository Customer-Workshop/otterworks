run_id: single-session-wave-3
manifest_sha: 7e99bf91c58c

# Wave 3 independent reconciliation (playbook 4 Part 1)

- Engagement: offline OW_BILLING (Oracle) -> MongoDB, run branch `tp-run/mongodb-20260926T164803Z-rt-offline` @ `a28ba801`
- Access axes: source_access=`ddl_only`, target_access=`local` (`waves/wave-3.json`)
- Verifier: independent session (migrated nothing; read only the run branch, `--w3-b01` @ `6232d4e0`, `--w3-b02` @ `468bb75b`, the wave-0 recon report for shape, and `tech-partnerships` for the Oracle Makefile; child chats and PR bodies not read; loaders, gates, parity replays re-executed from the spec on a fixture built on the verifier machine)
- Inputs: `03_mapping_spec.json` map-draft-3.1, `02_tolerances.json` tol-2, `waves/wave-3.json`, `fixtures/ow_billing_demo.json`, `allowed_targets.json`; unit code + committed evidence under `services/legacy-billing/migration/mongo/` on each child branch
- Harness: mongo-recon-harness 0.3.2 from the mongo-migration plugin 0.3.0, fresh venv (`recon selftest PASS: 9 canonicalization rules exercised`); oracledb 26.0.1, pymongo 4.18.2

## Wave verdict

**fixture PASS, live recon pending customer run.** Rehearsal evidence only: every gate ran `--mode fixture --target-class local`, `merge_eligible=false` in all five result.json. Nothing was merged; nothing may merge on this evidence (AGENTS.md rule 11). Two low-severity code findings (F1, F2) surfaced by probes past the gate; neither is reachable from the fixture or the transcripts, neither changes a unit verdict, both go to the unit owners.

| Batch | Unit | Oracle objects | Spec collections (verifier subset) | Gate (verifier re-run) | Parity replay | Verifier verdict | Agrees with child evidence |
|---|---|---|---|---|---|---|---|
| w3-b01 | u-07-plsql-util | PKG_OW_UTIL | codes, billingAuditLog | T1 2 / T2 1 / T3 32 / T4 2, all PASS | 0 mismatches (f_code_desc x33, f_md5_uuid x2, dt2str/str2dt, log_msg) | **PASS** (fixture, local) | yes (tier-for-tier); version label differs, see D1 |
| w3-b01 | u-08-plsql-plans | PKG_PLANS, TRG_SUBSCRIPTIONS_HIST, TRG_SUB_NO_UNCANCEL | tenants, plans, subscriptions, subscriptionsHist | T1 4 / T2 10 / T3 143 / T4 4, all PASS | PLANS-001..005 5/5 PASS, regenerated `*.mongo.json` byte-identical to committed | **PASS** (fixture, local) | yes; version label differs, see D1 |
| w3-b02 | u-09-plsql-rating | PKG_RATING | ratingPeriods, ratingResults | T1 2 / T2 8 / T3 6 / T4 2, all PASS | RATING-001..008 8/8 PASS | **PASS** (fixture, local) | yes |
| w3-b02 | u-10-plsql-invoicing | PKG_INVOICING | ratingPeriods, ratingResults, invoices, creditNotes | T1 5 / T2 16 / T3 19 / T4 3, all PASS | INVOICE-001..006 6/6 PASS | **PASS** (fixture, local) | yes |
| w3-b02 | u-11-plsql-dunning | PKG_DUNNING, JOB_NIGHTLY_DUNNING | tenants, subscriptions, dunningAttempts, notifications, subscriptionsHist | T1 5 / T2 10 / T3 142 / T4 3, all PASS | DUNNING-001..005 5/5 PASS (DUNNING-002/003 `*.mongo.json` differ from committed by key order only, see D2) | **PASS** (fixture, local) with finding F2 | yes |

Quarantine: 0 on every loader run (the loaders have no quarantine path; every source row mapped). Full recon runs used: 1 per unit (cap 3).

## Independent re-run (both batches)

1. Fixture rebuilt on the verifier machine from a throwaway `tech-partnerships` worktree: `make oracle-billing-up && make oracle-billing-seed NS=demo` (Oracle Free 23, schema OW_BILLING, seed 714559852, batch 85559852; CODES=32, PLANS=3, SUBSCRIPTIONS=70, INVOICES=4, USAGE_EVENTS=817, RATING_PERIODS=3, DUNNING_ATTEMPTS=1 — matches `fixtures/ow_billing_demo.json`). Source never modified; every Oracle call in this report is a SELECT or a read-only function (`callfunc`), one connection per script.
2. Local target: `docker run -d --name ow-mongo -p 27017:27017 mongo:7`. Databases present afterwards: `admin, config, local, ow_billing_migration` only. Collections in `ow_billing_migration`: the 12 spec collections the loaders drop+recreate plus the declared scratch collections `parity_w3_b01` / `parity_w3_b02` (emptied by the loaders). Secrets referenced by name only (`OW_BILLING_FIXTURE_DSN`, `MONGO_LOCAL_URI`); every command prefixed `env -u MONGODB_ATLAS_URI`.
3. Subset-spec verification: for each unit, the committed `recon/<unit>/mapping.subset.json` was compared object-for-object with the run-branch `03_mapping_spec.json` (map-draft-3.1). All five: the `collections[]` entries and the `canonicalization` block are verbatim copies of the run-branch objects. u-09/u-10/u-11 also carry `version: map-draft-3.1` / `map-draft-3.1-canon`. u-07/u-08 carry `version: map-draft-2` / `map-draft-2-canon` (deviation D1). The verifier gate ran its own subsets, cut from the run-branch spec with the same collection lists (`<unit>/mapping.subset.verifier.json`), so every result.json here reads `mapping_version=map-draft-3.1`.
4. w3-b01: `fixture_load.py` from `--w3-b01` -> `codes 32, plans 3, tenants 70, subscriptions 70, subscriptionsHist 0, billingAuditLog 0`. Gate per brief for u-07 and u-08 (`recon run --unit <u> --family oracle --mapping <subset> --tolerances .migration/02_tolerances.json --canonicalization profiles/oracle.md --mode fixture --target-class local --source-dsn-secret OW_BILLING_FIXTURE_DSN --target-uri-secret MONGO_LOCAL_URI --target-db ow_billing_migration --allowed-targets-file .migration/allowed_targets.json --ops ops/<u>.ops.json --source-concurrency 1 --seed 1`) -> exit 0, PASS, tier counts in the table, `redacted=true`, `redaction_salted=false`, `merge_eligible=false`. `parity_w3_b01.py` -> `u-07 PASS mismatches=0`, `u-08 PASS 5/5`, target left at baseline, `git status` on the child worktree clean (regenerated evidence identical to committed).
5. w3-b02: `fixture_load.py` from `--w3-b02` -> the six b01 collections plus `usageEvents 817, ratingPeriods 3, ratingResults 3, invoices 4, creditNotes 5, dunningAttempts 1, notifications 1`. Gate for u-09, u-10, u-11 with the same command shape and the unit `--ops` files -> exit 0, PASS, tier counts in the table, `merge_eligible=false`. `parity_w3_b02.py` -> 19/19 scenarios PASS (8 rating, 6 invoicing, 5 dunning; DUNNING-005 replays `sp_suspend_overdue` twice per the transcript). Full replay output: `parity_w3_b02.replay.json`.
6. Tier-for-tier comparison with the committed `recon/<unit>/recon.summary.md` + `result.json` on the child branches: identical verdicts, identical tier check counts for all five units, same tolerances `tol-2`, same seed 1. Only difference: mapping_version label on u-07/u-08 (D1).

## Probes past the gate

Scripts: `probe_w3_b01.py`, `probe_w3_b02.py`; raw results `probes_w3_b01.json`, `probes_w3_b02.json`. Each script reloads the Mongo fixture from Oracle between probes and at the end.

| Batch | Probe | Result | Note |
|---|---|---|---|
| w3-b01 | P1 TRG_SUB_NO_UNCANCEL: open cancelled sub through `change_plan` | PASS | closed sub keeps `statusCd=30`, `endsOn=eff-1`, new sub `statusCd=10`; open suspended sub -> `10` per `DECODE(status,30,30,10)`. The fixture has no open cancelled subscription and no PLANS transcript covers one, so the cancelled row was synthesised in the Mongo copy (see "Not covered") |
| w3-b01 | P2 TRG_SUBSCRIPTIONS_HIST: hist rows per UPDATE | PASS | exactly one `UPD` row per closed sub, full OLD copy, `hist_id` monotonic 1..n across two successive `change_plan` calls |
| w3-b01 | P3 `change_plan` replayed with identical args | PASS | second call raises `DuplicateKeyError` on the deterministic `f_md5_uuid` id, mirroring ORA-00001 on the PK |
| w3-b01 | P4 `fn_entitlement` boundaries | PASS | `endsOn` day inclusive with `effective_on=GREATEST(startsOn, on)`; day before `startsOn` -> empty; unknown tenant -> empty |
| w3-b01 | P5 PKG_OW_UTIL edge inputs vs Oracle (read-only) | FAIL -> F1 | `f_md5_uuid` on empty / 1-char / unicode / 300-char inputs, `f_dt2str(NULL)`, `f_str2dt(NULL)`, `f_dt2str(1999-12-31)`, `f_code_desc(STATUS,10)` all match; `f_code_desc(STATUS, NULL)` Oracle `UNKNOWN(-1)` vs Mongo `TypeError` |
| w3-b02 | P1 read-only sweep: `fn_usage_rating`, `fn_usage_summary`, `fn_invoice_preview` for all 70 usage tenants + 1 unknown tenant x 4 monthly periods (Nov-25..Feb-26) | PASS | 852 refcursor-vs-service comparisons, 0 mismatches (covers empty periods, no-plan tenants, rollover, tiered overage, credit cap) |
| w3-b02 | P1b `fn_invoice_lines` for every invoice; `fn_overdue_accounts` for 5 as_of values incl. issue-day boundary | PASS | 0 mismatches |
| w3-b02 | P2 JOB_NIGHTLY_DUNNING double call, same as_of | PASS | `schedule_dunning` appends `attempt_no+1` on each call (1 -> 3 -> 5 attempts; this is Oracle's `NVL(MAX)+1` semantics, not a bug); `suspend_overdue` suspends 1 tenant on the first call and none on the second; kind-3 notifications, hist rows and suspended-tenant count unchanged by the second call |
| w3-b02 | P3 `sp_suspend_overdue` cutoff day-granularity | FAIL -> F2 | invoice with `issuedAt` 2026-02-13 10:00, as_of 2026-02-27 (cutoff 02-13): Oracle `TO_CHAR(issued_at,'YYYYMMDD') <= TO_CHAR(TRUNC(as_of)-14,'YYYYMMDD')` includes it (verified with a read-only expression on the fixture DB); Mongo `issuedAt <= midnight(cutoff)` excludes it |
| w3-b02 | P4 `schedule_dunning` weekend push-out | PASS | Fri -> Fri, Sat -> Mon (+2), Sun -> Mon (+1) |
| w3-b02 | P5 `issue_invoice` replayed for same tenant/period | PASS | one invoice, second call re-issues in place (DUP_VAL_ON_INDEX path) |

## App-level parity replay

Both transcript replays were executed independently (step 4/5) with the child scripts unmodified against the transcripts under `procs/oracle/transcripts/{plans,rating,invoicing,dunning}` (ORACLE_SOURCE_SHA `0d326cad...`). 24/24 scenarios PASS. Read-only Oracle functions were additionally compared live against the service code beyond the transcripts (P5 b01, P1/P1b b02); the write procedures (`sp_change_plan`, `sp_finalize_rating`, `sp_issue_invoice`, `sp_schedule_dunning`, `sp_suspend_overdue`) were not executed on Oracle (source read-only), so their Mongo behaviour is judged against the transcripts and against the PL/SQL text.

## Findings (none blocking the fixture verdict)

- **F1 (low, u-07 code):** `ow_util.code_desc(db, type, None)` raises `TypeError` (`int(None)`) where `pkg_ow_util.f_code_desc(type, NULL)` returns `'UNKNOWN(-1)'`. The function body already contains the `-1` fallback but `int(code_val)` runs first. Only caller is `rating_service.usage_summary` with `kind_cd` from `usageEvents`, which `TRG_USAGE_EVENTS_CHECK` keeps non-null, so unreachable from the fixture and the transcripts. Evidence: probe b01 P5.
- **F2 (low, u-11 code):** `dunning_service.suspend_overdue` compares `issuedAt <= midnight(as_of-14)`; the PL/SQL compares at day granularity (`TO_CHAR ... 'YYYYMMDD' <=`). An invoice issued with a time-of-day on the cutoff day is suspended by Oracle and skipped by Mongo. `sp_issue_invoice`/`issue_invoice` always write `issued_at = CAST(period_end AS TIMESTAMP)` (midnight) and the fixture has 0 non-midnight rows, so unreachable today; a live source with externally inserted invoices could hit it. `fn_overdue_accounts` (`<` vs `TO_CHAR <`) is equivalent and unaffected. Evidence: probe b02 P3.
- **F3 (info):** `redaction_salted=false` in all result.json (verifier and children); `RECON_REDACT_SALT` unset in this offline engagement, acceptable for the synthetic fixture, must be set for the live run.
- **F4 (info):** neither child branch touches `.migration/` relative to the run branch (`git diff --stat run...child -- .migration` empty), consistent with rule 6.
- **F5 (info):** Tier 4 `--ops` for the code units are read-side projections (codes lookup, audit rows, plans/subscriptions listings, rating/invoice/dunning rows); the procedure semantics are covered by the transcript replay and the probes above, not by the harness.

## Deviations

- **D1 (evidence metadata, w3-b01):** committed `recon/u-07-plsql-util/mapping.subset.json` and `recon/u-08-plsql-plans/mapping.subset.json` (and hence the committed result.json) carry `version: map-draft-2` / `map-draft-2-canon` while the run branch is at `map-draft-3.1`. Collection objects and canonicalization rules are verbatim map-draft-3.1 (the 3.1 change, `target_where` on `invoices.lines.lineNo`, does not touch these collections), so the gate content is identical and the verifier re-ran under the 3.1 label. The child branch should relabel its subsets before any live run so the evidence version matches the spec in force.
- **D2 (reproducibility, u-11):** re-running `parity_w3_b02.py` rewrote `recon/u-11-plsql-dunning/parity/DUNNING-002.mongo.json` and `DUNNING-003.mongo.json` with `business_fields` keys in a different order (content identical). `_scenario_fields` iterates a set; the artifact is not byte-reproducible. Cosmetic.
- **D3 (fixture coverage):** no open cancelled subscription exists in the demo fixture and no PLANS transcript exercises TRG_SUB_NO_UNCANCEL; probe P1 synthesised the row in the disposable Mongo copy (never in Oracle). A transcript for that case should be recorded from the customer's Oracle before the live run.
- **D4 (process):** the verifier ran the gates from the run-branch checkout with subsets cut from the run-branch spec rather than the committed child subset files, so that `mapping_version` in the verifier evidence reflects the spec in force; the committed subsets were verified object-for-object instead of being executed.

## Not covered / pending

- Live recon: not possible (source_access=ddl_only, no migration cluster). `--mode live --target-class migration_cluster` against the customer's Oracle and the Atlas migration cluster is the merge gate for u-07..u-11 and remains pending a customer run.
- Write-procedure parity on Oracle: `sp_*` procedures were not executed against the source (read-only); parity rests on the recorded transcripts plus PL/SQL reading.
- JOB_NIGHTLY_DUNNING scheduling itself (DBMS_SCHEDULER, disabled in the source) has no Mongo-side scheduler yet by design; only the job body was probed.

## Skill feedback

- `mongo-recon-harness`: the harness accepted a subset whose `version` differs from the run-branch spec without warning (D1). A `--expect-mapping-version` flag or a warning when the subset version does not match `.migration/03_mapping_spec.json` would catch this at gate time.
- `mongo-recon-harness` / playbook 4: for PL/SQL code units the Tier 4 `--ops` files can only express read projections; the playbook should say explicitly that transcript replay + behavioural probes (idempotency, trigger invariants, boundary dates) are the required complement, and give a probe list for procedure units.
- Playbook 4 Part 1: state that the verifier should evaluate day-granular date comparisons (`TO_CHAR(...,'YYYYMMDD')`, `TRUNC`) with non-midnight timestamps even when the fixture only has midnight values; that is how F2 was found and the gate cannot see it.
- Fixture (`oracle-billing-estate`): the demo seed has no cancelled-and-open subscription and no non-midnight `issued_at`; adding both would let the gates and transcripts cover TRG_SUB_NO_UNCANCEL and the dunning cutoff directly.
