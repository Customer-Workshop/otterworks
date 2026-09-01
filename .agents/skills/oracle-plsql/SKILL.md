---
name: oracle-plsql
description: Oracle SQL / PL/SQL to Databricks (Spark SQL) conversion rules for the OtterWorks Commission Pay COMMISSION_DW migration. Use when converting Oracle tables, materialized views or PL/SQL MERGE loaders into ow_tp Delta tables and Workflows, or when writing their recon.
---

# oracle-plsql → Databricks SQL (v0, wave 0 stub)

Scope: the dialect rules a `!dbx_unit_migration` child needs for `COMMISSION_DW`. Every
rule below is either taken from the field dictionary in `.migration/COMMISSION_DW_analysis.md`
§3 or from the target-state SQL profile. Extend this file via SKILL FEEDBACK, never fork it.

## Types
| Oracle | Databricks | Note |
|---|---|---|
| `NUMBER` identity key (`GENERATED ... AS IDENTITY`) | `BIGINT`, **explicit values** | never `GENERATED ALWAYS AS IDENTITY`; keys are carried over from the baseline snapshot (DEC-003) |
| `NUMBER(p,s)` | `DECIMAL(p,s)` | money is `DECIMAL(12,2)`; recon compares exact integer cents |
| `NUMBER(4,0)/(2,0)/(1,0)` | `INT` | |
| `NUMBER` unbounded (COUNT/SUM results) | `BIGINT` / `DECIMAL(22,2)` | Spark `SUM(DECIMAL(12,2))` widens to (22,2); compare in cents |
| `VARCHAR2(n)` | `STRING` | `period_month` stays a `YYYY-MM` string, never `DATE` |
| `DATE` | `DATE` | |
| `TIMESTAMP(6)` | `TIMESTAMP` | `SYSTIMESTAMP` → `current_timestamp()`; `loaded_at` is excluded from recon |

## Expressions
- `NVL(a,b)` → `coalesce(a,b)`; `DECODE` → `CASE`; `a || b` → `concat(a,b)`.
- `TRUNC(d,'MM')` → `date_trunc('MONTH', d)::date`.
- `TO_NUMBER(SUBSTR(s,1,4))` → `CAST(substr(s,1,4) AS INT)`. Oracle raises on malformed input,
  Spark returns NULL: every derived NOT NULL column must be guarded, e.g.
  `assert_true(count_if(year_num IS NULL) = 0)` before the MERGE.
- `CEIL(m/3)` → `CAST(ceil(m/3) AS INT)`.
- `ROUND(x,2)` on DECIMAL: Spark is HALF_UP like Oracle for positives; negatives need a named test.
- Empty string: Oracle `''` is NULL, Spark is not. Snapshots emit NULL as an empty CSV field and
  loads read empty as NULL (`read_files(..., mode => 'FAILFAST')` with explicit schema).

## Statements
- `MERGE INTO t USING (...) s ON (...) WHEN MATCHED THEN UPDATE SET ... WHEN NOT MATCHED THEN INSERT ...`
  translates 1:1 to Delta `MERGE INTO`. Keep the same ON key (business key), same UPDATE column
  list (do **not** add columns the legacy did not update, e.g. `fact_commission.product_key`).
- Insert-only MERGE (`WHEN NOT MATCHED` only) is valid Delta; keep it insert-only.
- New surrogate keys: `max(key) + row_number() OVER (ORDER BY <natural key>)` computed in the
  source subquery of the MERGE; the Workflow is the single writer, so this is collision-free.
- `SQL%ROWCOUNT` after MERGE → `num_affected_rows` from the MERGE result (`SELECT * FROM (MERGE ...)`
  on DBR 14+ / `DESCRIBE HISTORY` operationMetrics). Record it in `ow_tp.ops.run_log_<ns>`.
- `COMMIT` / `EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE` → there is no cross-table transaction.
  Model the procedure as an ordered Workflow task chain that **fails fast**: a failed task leaves
  earlier tables updated; the rerun is idempotent (MERGE) so re-running the whole job repairs.
  Never swallow errors (`WHEN OTHERS THEN NULL` has no equivalent and is forbidden).
- Inner joins that drop rows silently: count the dropped rows explicitly and fail or quarantine
  (`ow_tp.ops.quarantine_<ns>`) when nonzero (DEC-016).
- `CREATE MATERIALIZED VIEW ... REFRESH COMPLETE ON DEMAND` → gold Delta table rebuilt by
  `CREATE OR REPLACE TABLE ... AS SELECT` in the job's final task.
- `DBMS_MVIEW.REFRESH(mv,'C')` → run that final task.

## Unity Catalog / repo conventions
- Objects: `ow_tp.<bronze|silver|gold|ops>.<legacy_name>_<ns>`; landing volume
  `/Volumes/ow_tp/bronze/landing/<ns>/{feed,baseline}/`; serverless warehouse `565cd2fd713738c4`; no clusters.
- Bronze feed tables are refreshed by the job's first task from the manifest-pinned CSVs
  (see `scripts/tp_dbx/cdw_baseline.py load-feed` for the exact statement text).
- Recon: `python3 scripts/tp_dbx/cdw_recon.py --unit <unit> --ns <ns> --run-mode fixture --rerun "<load cmd>" --out dbx/commission_dw/<unit>`
  then `make tp-validate-recon FILE=dbx/commission_dw/<unit>/<unit>.recon.json`.
- Legacy Oracle is read-only: never DDL/DML, never grants.
