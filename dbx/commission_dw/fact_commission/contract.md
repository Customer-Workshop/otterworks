# Unit contract — `fact_commission` (COMMISSION_DW → `ow_tp.silver.fact_commission_cdw`)

Wave 2, batch B2-1. Target profiles: CORE + SQL + PIPELINE
(`.migration/COMMISSION_DW_target_state.md`); dialect rules:
`.agents/skills/oracle-plsql/SKILL.md`; tolerances v1
(`.migration/03_recon_tolerances.md`).

## Source and targets

| Role | Object | Ownership |
|---|---|---|
| Legacy table | `COMMISSION_DW.FACT_COMMISSION` | production legacy warehouse, read-only |
| Feed | `ow_tp.bronze.commission_ledger_cdw` | Workflow T0 refresh; read-only to U4 |
| Baseline | `/Volumes/ow_tp/bronze/landing/cdw/baseline/FACT_COMMISSION.csv` | manifest-pinned, 3 rows |
| Target | `ow_tp.silver.fact_commission_cdw` | U4 only |
| Evidence | `ow_tp.ops.run_log_cdw`, `ow_tp.ops.quarantine_cdw` | U4 loader |

## Mapping

| Oracle type / column | Databricks type / column | Rule |
|---|---|---|
| `fact_id NUMBER` identity | `fact_id BIGINT NOT NULL` | baseline value verbatim (DEC-003); new values are allocated only over unmatched rows |
| `agent_key NUMBER` | `agent_key BIGINT NOT NULL` | dimension key carried from the target dimension |
| `product_key NUMBER` | `product_key BIGINT NOT NULL` | product dimension key; not updated on a matched row |
| `period_key NUMBER` | `period_key BIGINT NOT NULL` | period dimension key |
| `policy_id NUMBER` | `policy_id BIGINT NOT NULL` | MERGE business key component |
| `split_pct NUMBER(5,2)` | `split_pct DECIMAL(5,2) NOT NULL` | exact decimal |
| `base_premium NUMBER(12,2)` | `base_premium DECIMAL(12,2) NOT NULL` | exact cents |
| `commission_amt NUMBER(12,2)` | `commission_amt DECIMAL(12,2) NOT NULL` | exact cents |
| `loaded_at TIMESTAMP` | `loaded_at TIMESTAMP NOT NULL` | `current_timestamp()`, excluded from recon |

Write targets are limited to the fact table and the two U4 evidence tables. No schema,
catalog, grant, cluster, or unprefixed object is created.

## Semantics preserved

- MERGE key is `(policy_id, agent_key, period_key)` (`UX_FACT_ROW`).
- Matched rows update exactly `split_pct`, `base_premium`, `commission_amt`, and `loaded_at`;
  `product_key` is not updated. Unmatched rows insert all fact attributes.
- Each run drops and rebuilds the fact from the baseline, then MERGEs the feed snapshot.
  A run with no period parameter processes all periods; `--period-month` applies the
  legacy `p_period_month` predicate.
- `fact_id` values from the baseline are preserved. New identifiers use
  `max(fact_id) + row_number()` over unmatched rows only.
- `SQL%ROWCOUNT` is represented by the MERGE result's `num_affected_rows`; update and insert
  metrics are also retained in `run_log_cdw`.

## Ambiguity classes

| Class | Policy |
|---|---|
| Encoding | UTF-8 input and output; strings are compared byte-for-byte after UTF-8 normalisation |
| Malformed records | Explicit CSV schemas with `FAILFAST`; type and field-shape errors abort. NULLs in NOT NULL fact columns are rejected by assertions |
| Empty input | Empty ledger means MERGE no-op, fact equals baseline, and summary rebuilds from fact. Empty baseline plus empty feed yields empty tables and is legitimate |
| Batch granularity | Full snapshot per run; optional `p_period_month` maps to the `period_month` job parameter; the Workflow is the single writer |

## Join-drop handling and atomicity

Rows that fail the policy, agent, product, or period inner joins are written to
`quarantine_cdw` with attribution and the run fails before MERGE. The failed run receives a
`run_log_cdw` row with `status = 'FAILED'` and `dropped_join_rows`.

The Oracle COMMIT/ROLLBACK spanned dimensions and fact. Delta uses ordered fail-fast tasks
T0→T5 instead: a failed task leaves earlier tables refreshed, and a full rerun repairs
them because each step is drop-and-rebuild or idempotent MERGE. The Workflow is the single
writer and its schedule is PAUSED; the schedule is only a carrier and never runs automatically.

`run_log_cdw` columns are `run_id`, `unit`, `period_month`, `rows_merged`, `rows_updated`,
`rows_inserted`, `dropped_join_rows`, `status`, `detail`, `started_at`, and `finished_at`.

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
python3 scripts/tp_dbx/cdw_recon.py --unit fact_commission --ns cdw --run-mode fixture \
  --baseline-dir etl/legacy-extra/commission_dw/cdw --out dbx/commission_dw/fact_commission/recon/ \
  --rerun "python3 dbx/commission_dw/fact_commission/run.py --run-job --ns cdw"
make tp-validate-recon FILE=dbx/commission_dw/fact_commission/recon/fact_commission.recon.json
```

PASS requires exact row count, duplicate and NULL checks, row-level equality, exact money
sums, `fact_covers_ledger`, and an actual idempotency rerun.
