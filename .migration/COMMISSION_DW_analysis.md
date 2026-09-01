# Pipeline analysis — P1 Commission DW (`COMMISSION_DW` → `ow_tp.*_cdw`)

Pipeline chosen at STOP B (2026-09-01). Sources cited: `services/industry-solutions/insurance/db/olap/01_star_schema.sql` (DDL), `olap/02_etl_pkg.sql` (loader + MV), Oracle catalog probes of instance `cdw` (`ALL_TAB_COLUMNS`, `ALL_IND_COLUMNS`, `ALL_DEPENDENCIES`, `ALL_MVIEWS`), `COMMISSION_DW_inventory.md`, target state `COMMISSION_DW_target_state.md` (CORE, SQL, PIPELINE, DATA/DEPENDENCY profiles — all present).

## 1. Pinned scope
Entry feeds: `COMMISSION_PAY.AGENTS`, `PRODUCTS`, `POLICIES`, `COMMISSION_LEDGER` (read-only, D3-1). Transformation: `DW_ETL_PKG.LOAD_COMMISSION_FACTS(p_period_month DEFAULT NULL)` — four sequential MERGEs (`02_etl_pkg.sql` L23–85), one transaction, `COMMIT` on success, `ROLLBACK; RAISE` on any error. Terminal outputs: `DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION`, `MV_AGENT_COMMISSION_SUMMARY` (`REFRESH COMPLETE ON DEMAND`, L99–113). Exclusions: `COMMISSION_PAY.COMMISSION_PKG` and all OLTP logic (DEC-001); identity sequences and constraint indexes are not migrated as objects. Nothing absent, nothing unreachable.

## 2. Unit inventory
| Unit | Source | Workload | Reads | Writes | Complexity | Shared | Risk flags |
|---|---|---|---|---|---|---|---|
| U1 `dim_agent` | `01_star_schema.sql` (DDL); `02_etl_pkg.sql` L23–33 (MERGE) | SQL + PIPELINE step | `COMMISSION_PAY.AGENTS` | `ow_tp.silver.dim_agent_cdw` | S | no | identity key preservation; MERGE updates 3 attrs |
| U2 `dim_product` | DDL; L35–44 | SQL + PIPELINE step | `COMMISSION_PAY.PRODUCTS` | `ow_tp.silver.dim_product_cdw` | S | no | natural key `product_code` |
| U3 `dim_period` | DDL; L46–57 | SQL + PIPELINE step | `COMMISSION_PAY.COMMISSION_LEDGER` (DISTINCT `period_month`) | `ow_tp.silver.dim_period_cdw` | S | no | **insert-only MERGE (no WHEN MATCHED)**; `SUBSTR`/`TO_NUMBER`/`CEIL` derivations; period filter `p_period_month IS NULL OR =` |
| U4 `fact_commission` + loader job | DDL; L59–87; whole procedure as the job | PIPELINE (money path) | ledger ⋈ policies ⋈ dim_agent ⋈ dim_product ⋈ dim_period | `ow_tp.silver.fact_commission_cdw`; job `ow_tp_cdw_load_commission_facts` (tasks: U1→U2→U3→U4 MERGEs, then U5 rebuild) | M | no | **inner joins drop ledger rows with unknown agent/product/period silently**; WHEN MATCHED does **not** update `product_key`; `loaded_at` server-side; `SQL%ROWCOUNT` = fact MERGE rows only; NUMBER(12,2) money; transaction atomicity (all-or-nothing) has no Delta equivalent across 4 tables |
| U5 `mv_agent_commission_summary` | L99–113 | SQL (report/aggregate) | U1–U4 targets | `ow_tp.gold.mv_agent_commission_summary_cdw` | S | no | `COUNT(*)`, `SUM` on DECIMAL → `NUMBER` unbounded on legacy; full rebuild semantics; result ordering nondeterministic |

W0 (shared/scaffolding, not units): catalog + schemas + volume; bronze snapshots of 9 objects; dialect skill stub; preflight 10/10; recon harness script.

## 3. Field / type dictionary (FACT = from `ALL_TAB_COLUMNS`; rule from target-state SQL profile)
| Table | Column | Legacy | Target | Status | Note |
|---|---|---|---|---|---|
| dim_agent | agent_key | NUMBER (identity) | BIGINT (explicit value from snapshot) | FACT | DEC-003; never `GENERATED ALWAYS` |
| dim_agent | agent_id | NUMBER | BIGINT | FACT | source key |
| dim_agent | agent_code / full_name / status | VARCHAR2(16/120/12) | STRING | FACT | |
| dim_product | product_key | NUMBER (identity) | BIGINT | FACT | |
| dim_product | product_code / product_name / line_of_business | VARCHAR2(16/120/24) | STRING | FACT | |
| dim_period | period_key | NUMBER (identity) | BIGINT | FACT | |
| dim_period | period_month | VARCHAR2(7) | STRING (`YYYY-MM`) | FACT | never DATE |
| dim_period | year_num / month_num / quarter_num | NUMBER(4,0)/(2,0)/(1,0) | INT | FACT | `CEIL(m/3)` → `ceil(m/3)` cast INT |
| fact_commission | fact_id | NUMBER (identity) | BIGINT | FACT | |
| fact_commission | agent_key / product_key / period_key / policy_id | NUMBER | BIGINT | FACT | |
| fact_commission | split_pct | NUMBER(5,2) | DECIMAL(5,2) | FACT | |
| fact_commission | base_premium / commission_amt | NUMBER(12,2) | DECIMAL(12,2) | FACT | money; recon in integer cents |
| fact_commission | loaded_at | TIMESTAMP(6) | TIMESTAMP | FACT | `current_timestamp()`; excluded from recon (DEC-004) |
| mv_summary | agent_code / full_name / period_month / line_of_business | VARCHAR2 | STRING | FACT | |
| mv_summary | policy_rows | NUMBER (from COUNT(*)) | BIGINT | **INFERRED** | Oracle COUNT is unbounded NUMBER |
| mv_summary | total_commission | NUMBER (SUM of 12,2) | DECIMAL(22,2) | **INFERRED** | Spark SUM(DECIMAL(12,2)) widens to (22,2); compared in cents so width is irrelevant to parity |
| bronze (9 snapshot tables) | all | as above + `COMMISSION_PAY` types (`DATE`→DATE, `TIMESTAMP(6)`→TIMESTAMP) | CSV-typed on load via explicit schema | FACT | identical names, `_cdw` suffix |

Engine quirks (named risks): (a) Oracle empty string = NULL vs Spark `''` ≠ NULL — snapshots must emit NULL as empty field and loads must read empty as NULL, all `NOT NULL` columns so exposure is nil for DW tables; (b) `TO_NUMBER(SUBSTR(...))` on malformed `period_month` raises in Oracle, returns NULL in Spark — the converted `dim_period` step must fail on NULL derivations (`assert_true`) to preserve the rollback semantic; (c) `ROUND` not used in P1 — the negative-rounding test from the tolerance record is N/A (recorded).

## 4. Dependency table (register mode; decisions at STOP C)
| ID | Class | Contract | Lead time | Status |
|---|---|---|---|---|
| D3-1 | D3 upstream feed | `COMMISSION_PAY.{AGENTS,PRODUCTS,POLICIES,COMMISSION_LEDGER}`, batch, read-only; no federation reach (loopback) → bronze snapshot per run; at cutover the feed is a customer-run extract into `/Volumes/ow_tp/bronze/landing/cdw/feed/` | none (no external team) | UNDECIDED → option: snapshot ingestion contract |
| D4-1 | D4 consumer | MV/fact readers unknown (no query history, no grants) | n/a | UNDECIDED → option: accept gap, gold table + view exposure, re-point at cutover by customer |
| D5-1 | D5 scheduler | none exists; target Workflow deployed PAUSED, run by hand / by cutover | none | UNDECIDED → option: Workflow, paused |
| D8-1 | D8 governance | no grants/masks/policies; `full_name`, `holder_name` are person data | none | UNDECIDED → option: no UC masks, engagement-principal grants only |
| D10-1 | D10 federation | unreachable; DEGRADED snapshot recon | accepted at STOP A | DECIDED (DEC-002) |
| D10-2 | D10 catalog absent | wave 0 creates `ow_tp` + schemas + volume; preflight to 10/10 | none | DECIDED (wave 0) |
| D10-3 | D10 query history | not granted | accepted | DECIDED (accept) |
| D1 | intra-pipeline | U1,U2,U3 → U4 → U5 | — | ordering only |

## 5. Waves and fan-out batches
| Wave | Batch | Units | Write targets | Width |
|---|---|---|---|---|
| 0 (serial, parent) | W0 | catalog/schemas/volume; 9 bronze snapshots; dialect skill stub; recon harness; preflight | `ow_tp.{bronze,silver,gold,ops}`, `ow_tp.bronze.*_cdw` (9), volume | 1 |
| 1 (pilot) | B1-1 | U1 `dim_agent` | `ow_tp.silver.dim_agent_cdw` | 3 |
| 1 | B1-2 | U2 `dim_product` | `ow_tp.silver.dim_product_cdw` | |
| 1 | B1-3 | U3 `dim_period` | `ow_tp.silver.dim_period_cdw` | |
| 2 | B2-1 | U4 `fact_commission` + loader job, U5 `mv_agent_commission_summary` | `ow_tp.silver.fact_commission_cdw`, `ow_tp.gold.mv_agent_commission_summary_cdw`, job `ow_tp_cdw_load_commission_facts` | 1 |

Topological check: W0 → {U1,U2,U3} → U4 → U5; U4/U5 share a batch (FACT edge, same child). No two same-wave batches share a write target. Serial floor = W0 + 2 child waves + 2 parent recon windows. Legacy load: zero during waves (snapshot mode); wave 0 uses ≤2 Oracle sessions (cap honoured).

## 6. Recon plan per unit (DEGRADED; source of truth = `etl/legacy-extra/commission_dw/cdw/<object>.csv` + `manifest.json`, hash-pinned)
| Unit | Checks (one multi-metric statement per table) | Keys | Tier | Idempotency |
|---|---|---|---|---|
| U1 | rowcount = snapshot; row-level diff on `agent_key` over all 5 columns | `agent_key` (also `agent_id` unique) | full diff (<1M) | rerun MERGE step → 0 changed rows, identical diff |
| U2 | rowcount; row diff on `product_key` | `product_key` / `product_code` | full | same |
| U3 | rowcount; row diff on `period_key`; derived cols recomputed from `period_month` | `period_key` / `period_month` | full | same (insert-only semantics preserved) |
| U4 | rowcount; `SUM(commission_amt)`, `SUM(base_premium)`, `SUM(split_pct)` in cents/hundredths exact; row diff on `(policy_id, agent_key, period_key)` excluding `loaded_at`; declared source-volume assertion (ledger rows vs fact rows, with dropped-join count = 0 asserted) | `UX_FACT_ROW` | full | rerun for same period → row count unchanged, sums unchanged, `loaded_at` may change |
| U5 | rowcount; full result-set diff ordered by (`agent_code`,`full_name`,`period_month`,`line_of_business`); `SUM(total_commission)` in cents = fact sum | 4 grouping cols | full | rebuild twice → identical |
Determinism rule: all comparisons after `ORDER BY` the declared key; CSV snapshots are written ordered by the same key. Baseline volumes (after DEC-011 wave-0 run) are recorded in `manifest.json` and quoted in every child's hand-off as the declared source-volume assertion.

## 7. Risk list
1. **Empty ledger today** — baseline meaningless until DEC-011 executes (wave 0 gate: fact rows > 0, else halt and escalate).
2. Silent inner-join drops in U4: legacy drops orphan ledger rows without trace; converted job must count and assert `dropped = 0` (or quarantine to `ow_tp.ops.quarantine_cdw` and report) — recon row above.
3. `product_key` not updated on MATCHED — preserve exactly; a "cleaner" MERGE would diverge on reruns after product changes.
4. Cross-table atomicity: legacy is one transaction; target = ordered job tasks with `fail-fast`; a partial failure leaves dims loaded and fact stale — documented as accepted deviation (dims are idempotent, fact rerun heals) unless STOP C says otherwise.
5. INFERRED types on MV aggregates (cents comparison neutralises).
6. D4 consumers unknown — cutover re-point is customer-side; nothing here can prove consumer parity.
