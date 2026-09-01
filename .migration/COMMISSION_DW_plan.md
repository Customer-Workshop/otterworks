# Migration plan — P1 Commission DW (`COMMISSION_DW` → `ow_tp.*_cdw`)

Version 1, 2026-09-01, for STOP C. Inputs: `COMMISSION_DW_analysis.md` (current), `COMMISSION_DW_target_state.md` (CORE/SQL/PIPELINE/DATA present), `03_recon_tolerances.md` v1 (APPROVED at STOP A), `08_governance_inventory.md`. Approval sentence: **"STOP C approved"** (or name the row to change).

## 1. Dependency decisions (decide mode) — all PROPOSED, become DECIDED at STOP C
| ID | Decision | Routing point | Cutover condition | Decommission condition | Fired request | Owner |
|---|---|---|---|---|---|---|
| D3-1 feed | **Snapshot ingestion contract**: per run, the 4 `COMMISSION_PAY` inputs land as ordered UTF-8 CSV + `manifest.json` (sha256, rowcount, extraction ts) in `/Volumes/ow_tp/bronze/landing/cdw/feed/`; **the job's first task (T0, owned by U4) validates the manifest and replaces `ow_tp.bronze.<table>_cdw` atomically on every run** — a stale or invalid manifest fails the run before any silver task. Post-cutover the customer runs the same extract on their side (Auto Loader on the volume path is the ready hook). | the volume path | customer extract producing a valid manifest | legacy loader retired after parallel-run window | none needed (no external team) | engagement lead |
| D4-1 consumers | **Accept the evidence gap**; expose `ow_tp.gold.mv_agent_commission_summary_cdw` as the report surface; consumer re-point is a customer action at STOP E; no dual-publish | gold table name | customer names consumers or confirms none | — | none | customer |
| D5-1 scheduler | **Databricks Workflow `ow_tp_cdw_load_commission_facts`, deployed PAUSED**, parameter `period_month` (nullable = all); manual/cutover trigger only | the job | STOP E | — | none | engagement lead |
| D8-1 governance | **No UC masks/row filters** (none exist on legacy); grants = engagement principals `SELECT` on `ow_tp.gold.*_cdw` only; person data (`full_name`) stays clear-text as on legacy | UC grants | before any consumer re-point | — | none | engagement lead |
| D10-1/2/3 | already DECIDED (STOP A) | — | — | — | — | — |
No UNDECIDED entries remain once STOP C approves. No lead-time requests exist for this estate; none fired.

## 2. Scaffolding delta (wave 0, parent, serial)
| Item | What | Evidence |
|---|---|---|
| W0-1 | `CREATE CATALOG ow_tp` (if absent) ; schemas `bronze`,`silver`,`gold`,`ops`; managed volume `ow_tp.bronze.landing`; nothing unprefixed touched | SQL statement ids; `make tp-preflight-databricks` → 10/10 |
| W0-2 | DEC-011: run legacy's own workload once via its shipped procedures (`COMMISSION_PKG` calculation, `DW_ETL_PKG.LOAD_COMMISSION_FACTS`, `DBMS_MVIEW.REFRESH`) under `scripts/tp-run-deterministic.sh`; **gate: `FACT_COMMISSION` rows > 0**, else halt + escalate | Oracle counts before/after |
| W0-3 | Baseline extract (wave 0 only; per-run refresh is the job's T0 task): 9 objects → `etl/legacy-extra/commission_dw/cdw/<OBJECT>.csv` (ordered by declared key, UTF-8, NULL = empty, `TIMESTAMP` ISO-8601 UTC) + `manifest.json` (per file: rows, sha256, extracted_at, source object, order key); local check `FIXTURE_SOURCE=etl/legacy-extra/commission_dw/cdw make tp-fixture-land NS=cdw && make tp-fixture-verify NS=cdw`; upload via Files API to `/Volumes/ow_tp/bronze/landing/cdw/{feed,baseline}/`; sha256 re-read; `COPY INTO ow_tp.bronze.<obj>_cdw` for the 4 feed tables | manifest committed; upload log |
| W0-4 | Dialect skill stub `.agents/skills/oracle-plsql/SKILL.md`: the dictionary rules from analysis §3, MERGE→`MERGE INTO` mapping, insert-only MERGE, `SUBSTR/TO_NUMBER/CEIL`, empty-string/NULL, fail-on-NULL derivation, identity preservation, `SQL%ROWCOUNT` semantics, rollback→fail-fast task chain | file in run branch |
| W0-5 | Recon harness `scripts/tp_dbx/cdw_recon.py --unit <u> --ns cdw --run-mode fixture|live`: one multi-metric statement per table against the warehouse, compares to the baseline CSV, emits `<unit>.recon.json` (schema `recon-report.schema.json`) + `recon.summary.md`; `planted_anomaly_detections` = empty sets (none declared) | `make tp-validate-recon FILE=…` green on a dry run |
| W0-6 | Write-target ledger seeded with W0 targets in `05_progress.md`; CI: existing `tp-golden-smoke` on `tp-run/*` PRs (no new workflow) | ledger rows |
Data-load posture: materialized snapshot (federation impossible); all tables S-tier → CTAS/`COPY INTO`, no partitioned backfill.

## 3. Execution schedule
| Wave | Batch | Units | Branch | Size | Child | Isolated area |
|---|---|---|---|---|---|---|
| 1 pilot | B1-1 | U1 `dim_agent` | `migrate/commission-dw/w1-dim_agent` | S | 1 | `ow_tp.silver.dim_agent_cdw` |
| 1 pilot | B1-2 | U2 `dim_product` | `migrate/commission-dw/w1-dim_product` | S | 1 | `ow_tp.silver.dim_product_cdw` |
| 1 pilot | B1-3 | U3 `dim_period` | `migrate/commission-dw/w1-dim_period` | S | 1 | `ow_tp.silver.dim_period_cdw` |
| 2 | B2-1 | U4 `fact_commission` + job, U5 `mv_agent_commission_summary` | `migrate/commission-dw/w2-fact_and_summary` | M | 1 | `ow_tp.silver.fact_commission_cdw`, `ow_tp.gold.mv_agent_commission_summary_cdw`, job `ow_tp_cdw_load_commission_facts` |
- **Width**: 3 (wave 1), 1 (wave 2). Intake cap ≤3 pilot / ≤5 later — no wave exceeds 3. Dynamic workflow not used (<10 batches).
- **Legacy-query concurrency cap**: 2 sessions, wave 0 only; children have **zero live legacy budget** (snapshot mode).
- **Run-mode budget**: children iterate `run_mode: fixture` against the local fixture layer + their own isolated Delta tables; **one** parent `live` recon window per wave via `!dbx_data_reconciliation`.
- **Circuit breaker**: 3 same-class failures → halt launches, post `#ow-tp-alerts`. **Full re-run cap** 3 per unit; **review-round cap** 2 after self-check (repo policy).
- **Idempotency rule**: each child `DROP TABLE IF EXISTS` its own `*_cdw` targets and recreates at run start; never any other object.
- **Key initialisation rule (DEC-003)**: every silver table is created from its `COMMISSION_DW` baseline snapshot (bronze `dim_*_cdw` / `fact_commission_cdw` baseline copies) so `agent_key`, `product_key`, `period_key`, `fact_id` are carried over verbatim; the MERGE then only touches rows changed in the feed. New rows receive `max(key) + row_number() OVER (ORDER BY <natural key>)`, computed inside the MERGE's source subquery; the job is the single writer, so allocation is deterministic and collision-free. Recon asserts baseline-key preservation per table.
- **Pipelining**: wave 2's child may launch once all three wave-1 PRs are green and merged (U4 needs the dims' DDL); wave-1 independent recon runs concurrently with wave-2 conversion.
- **Parallel-run tiers**: U1–U3 short; U4 full window (money path) incl. one period-end boundary; U5 standard.
- **Wall-clock projection**: wave 0 ≈ 1 parent session-hour; wave 1 ≈ 1 child-hour in parallel + review (3 PRs, 2 rounds each) ≈ 1.5 h; wave 2 ≈ 1.5 h + review; recon windows ≈ 15 min each; parallel run ≥ 1 scheduled recon cycle; STOP turnaround dominates. Total ≈ 5–6 working hours of automation plus approvals. Reviewer: engagement lead, SLA same-day. Review tiering: recon-green + independent-recon PASS → light review (evidence-format + spot check); first unit of each class (U1 for dims, U4 for fact, U5 for report) gets full review.
- **Cost line** (recorded per unit at wave close in `05_progress.md`): session ACUs, warehouse-minutes; pilot measures, wave 2 re-baselined on it.

## 4. Batch hand-off packet (what each child receives — nothing else)
1. Batch id, unit list, branch name, PR title pattern `[CDW w<N>] <unit>: <what>`, base = `tp-run/databricks-20260901T205306Z`.
2. Pointers: `.migration/COMMISSION_DW_target_state.md` (CORE + SQL + PIPELINE + DATA), its §3 dictionary rows for the unit, `.agents/skills/oracle-plsql/SKILL.md`, `03_recon_tolerances.md`, this plan §5 gate.
3. Source: `services/industry-solutions/insurance/db/olap/01_star_schema.sql`, `02_etl_pkg.sql` line ranges from analysis §2.
4. Baseline: `etl/legacy-extra/commission_dw/cdw/<OBJECT>.csv` + `manifest.json` rows (declared source volumes quoted inline).
5. Target: catalog `ow_tp`, ns `cdw`, warehouse `565cd2fd713738c4`, secrets `DATABRICKS_DEMO_HOST`/`DATABRICKS_DEMO_TOKEN` (names only), capability manifest from W0-1 preflight, volume path.
6. Rules: register write targets in `05_progress.md` first; fixture-first; no legacy access; no shared DDL; no clusters; no requester identification; no demo/meta language; `tp-pre-pr-self-check` before opening; `make tp-smoke`, `make tp-validate-recon FILE=…` green.
7. Output layout: `dbx/commission_dw/<unit>/{ddl.sql,load.sql,contract.md,recon/<unit>.recon.json,recon/recon.summary.md}` (+ `job.json` for U4).

## 5. Recon gate (mechanical)
Command: `python3 scripts/tp_dbx/cdw_recon.py --unit <unit> --ns cdw --run-mode fixture --baseline-dir etl/legacy-extra/commission_dw/cdw --out dbx/commission_dw/<unit>/recon/` then `make tp-validate-recon FILE=dbx/commission_dw/<unit>/recon/<unit>.recon.json`.
PASS ⇔ every check `result: pass`: `rowcount` (exact), `row_diff` (0 differing rows on declared key, `loaded_at` excluded), money `sum_cents` (exact), U4 `dropped_join_rows = 0`, U5 `ordered_resultset_diff = 0`; `values_recomputed_from_target: true`; `idempotency_rerun.performed: true` with the rerun's row/sum evidence; `unverified_paths` lists at minimum `live-legacy-comparison (DEGRADED mode)` and, for U4, `cross-table transaction atomicity`; population per check = full table (all S-tier); baseline = wave-0 manifest hash quoted in the report header; declared source volume asserted per table.
PR body (≤2,000 chars): (1) decisions + unverified paths with owner/severity/closing gate, (2) code, (3) evidence = `recon.summary.md` rendered + link to JSON; then dependency entries IMPLEMENTED (U4: D3-1 read path; U5: D4-1 surface) and `SKILL FEEDBACK`.
Merge rule: recon-green per unit + parent live recon PASS for the wave + `tp-golden-smoke` green → merge; STOP D = notify `#ow-tp-status`.

## 6. Pilot and calibration
Wave 1 is the pilot (width 3, all three are the same "dimension MERGE" class, so one calibration unit is U1 — but they are launched together because they are independent and S; feedback from all three is harvested before wave 2). Wave 2 introduces two new classes (fact/money path, aggregate report) in one child — it is the calibration unit for both, and the last wave, so no further fan-out follows.

## 7. Governance mapping
| Legacy row | UC mapping | Status |
|---|---|---|
| G1/G2 `PUBLIC INHERIT PRIVILEGES` | none (Oracle default, no data access) | N/A |
| G3 owner system privs | ownership of `ow_tp.*_cdw` objects by the engagement principal | MAPPED |
| G5 reads of `COMMISSION_PAY` | replaced by the snapshot feed (D3-1) | MAPPED |
| G6 no masks / policies | none | MAPPED |
| — | `GRANT SELECT ON ow_tp.gold.mv_agent_commission_summary_cdw TO <engagement principals>` | PROPOSED (D8-1) |
GAP rows: none. Security reviewer: N/A (DEC-009).

## 8. Risk register
| Risk | Mitigation | Owner |
|---|---|---|
| Empty legacy ledger → vacuous baseline | DEC-011 wave-0 gate `fact rows > 0` | parent |
| Silent join drops (U4) | asserted `dropped_join_rows = 0` in recon; quarantine table if ever >0 | B2-1 child |
| `product_key` not refreshed on MATCHED | dictionary rule; rerun test in recon | B2-1 |
| Cross-table atomicity deviation | accepted: fail-fast task chain + idempotent rerun; listed as unverified path | STOP C |
| INFERRED MV aggregate types | cents comparison | B2-1 |
| Shared PAT / contended workspace | isolated `_cdw` objects; live proof only in the parent's window | parent |
| Files-scope or catalog-permission denial | preflight 10/10 is a wave-0 exit gate | parent |
| Unknown consumers (D4-1) | accepted gap; customer re-point at STOP E | customer |
