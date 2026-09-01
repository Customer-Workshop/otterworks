# Unit contract — `mv_agent_commission_summary` (COMMISSION_DW → `ow_tp.gold.mv_agent_commission_summary_cdw`)

Wave 2, batch B2-1. Target profiles: CORE + SQL + PIPELINE
(`.migration/COMMISSION_DW_target_state.md`); dialect rules:
`.agents/skills/oracle-plsql/SKILL.md`; tolerances v1
(`.migration/03_recon_tolerances.md`).

## Source and target

| Role | Object | Ownership |
|---|---|---|
| Legacy materialized view | `COMMISSION_DW.MV_AGENT_COMMISSION_SUMMARY` | production legacy warehouse, read-only |
| Source fact | `ow_tp.silver.fact_commission_cdw` | U4 output, read-only |
| Target | `ow_tp.gold.mv_agent_commission_summary_cdw` | U5 only |

## Mapping

| Oracle column / expression | Databricks column / type | Rule |
|---|---|---|
| `da.agent_code VARCHAR2(16)` | `agent_code STRING NOT NULL` | byte-exact dimension value |
| `da.full_name VARCHAR2(120)` | `full_name STRING NOT NULL` | byte-exact dimension value |
| `dd.period_month VARCHAR2(7)` | `period_month STRING NOT NULL` | `YYYY-MM`, never converted to DATE |
| `dp.line_of_business VARCHAR2(24)` | `line_of_business STRING NOT NULL` | byte-exact dimension value |
| `COUNT(*)` | `policy_rows BIGINT NOT NULL` | exact row count |
| `SUM(f.commission_amt)` | `total_commission DECIMAL(38,2) NOT NULL` | exact cents |
| refresh timestamp | `loaded_at TIMESTAMP NOT NULL` | `current_timestamp()`, excluded from recon |

The only write target is `ow_tp.gold.mv_agent_commission_summary_cdw`.

## Semantics preserved

The target is rebuilt completely on each `load_commission_facts` run, equivalent to Oracle
`REFRESH COMPLETE`. It groups the four declared dimensions exactly as the legacy view.
An assertion compares the sum of summary `policy_rows` to the fact row count, preventing
dimension joins from silently dropping facts. No schedule runs automatically: the PAUSED
schedule is only the Workflow carrier.

## Ambiguity classes

| Class | Policy |
|---|---|
| Encoding | UTF-8 input and output; strings are compared byte-for-byte after UTF-8 normalisation |
| Malformed records | Upstream explicit schemas use `FAILFAST`; summary NOT NULL output is asserted through the fact and dimension contracts |
| Empty input | Empty ledger means fact equals baseline and summary rebuilds from fact. Empty baseline plus empty feed yields empty tables and is legitimate |
| Batch granularity | Full snapshot per run; optional `p_period_month` maps to the Workflow job parameter; the Workflow is the single writer |

## Cross-table atomicity

The legacy COMMIT/ROLLBACK spanned dimensions and fact. Delta uses ordered fail-fast tasks
T0→T5: an earlier successful task remains refreshed if a later task fails, and a full rerun
repairs the chain because every step is drop-and-rebuild or MERGE.

## Coverage gaps / unverified paths

| Path | Owner | Severity | Closes at |
|---|---|---|---|
| live-legacy-comparison (DEGRADED mode) | parent | medium | wave-2 independent recon window |
| cross-table transaction atomicity | parent | medium | parallel run |
| new `fact_id` allocation exercised only by code review (feed has no rows absent from baseline) | U4 | low | first new ledger key |
| `period_month` filter path run only with NULL (all periods) | U4 | low | period-scoped run |
| `dropped_join_rows > 0` (quarantine + FAILED run log) | U4 | medium | read-only dry probe if safe; otherwise remains unverified |
| harness has no `dropped_join_rows` check id; `fact_covers_ledger` (ledger rows == fact rows) is the mechanical proxy, with dropped count in `run_log` | parent | info | harness enhancement |

## Recon gate

```
python3 scripts/tp_dbx/cdw_recon.py --unit mv_agent_commission_summary --ns cdw --run-mode fixture \
  --baseline-dir etl/legacy-extra/commission_dw/cdw --out dbx/commission_dw/mv_agent_commission_summary/recon/ \
  --rerun "python3 dbx/commission_dw/mv_agent_commission_summary/run.py --ns cdw"
make tp-validate-recon FILE=dbx/commission_dw/mv_agent_commission_summary/recon/mv_agent_commission_summary.recon.json
```

PASS requires exact row count, duplicate and NULL checks, row-level equality, exact money
sums, and an actual idempotency rerun.
