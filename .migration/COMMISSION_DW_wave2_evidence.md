# Wave 2 (close, width 1) — evidence brief

- **Run branch:** `tp-run/databricks-20260901T205306Z`
- **Merged PR:** #1431 (`migrate/commission-dw/w2-fact_and_summary`), merge `416f53b6`
- **Child session:** `f06d0fb25756476995641391a588b722`
- **Merge date:** 2026-09-01

## What landed

- `ow_tp.silver.fact_commission_cdw`: initializes from the `FACT_COMMISSION`
  baseline, then MERGEs on `(policy_id, agent_key, period_key)`. Matched rows
  update `split_pct`, `base_premium`, `commission_amt`, and `loaded_at`.
  New `fact_id` values use `max(fact_id) + row_number()` over unmatched rows.
- `ow_tp.gold.mv_agent_commission_summary_cdw`: `CREATE OR REPLACE TABLE … AS
  SELECT` grouped by `agent_code`, `full_name`, `period_month`, and
  `line_of_business`, with `policy_rows BIGINT` and
  `total_commission DECIMAL(38,2)`.
- `ow_tp.ops.quarantine_cdw` and `ow_tp.ops.run_log_cdw`.
- Workflow `ow_tp_cdw_load_commission_facts`, job `939320833644147`, PAUSED,
  with serverless notebook tasks T0 feed refresh → T1 dim_agent → T2
  dim_product → T3 dim_period → T4 fact → T5 summary. No clusters.

Successful end-to-end runs were `229329575176225`,
`1001284523437738` (idempotency), `129463628165955`, and
`569403231580155` (post-review). `dropped_join_rows = 0`.

## Recon evidence

| Unit | Child recon | Parent independent recon | Baseline manifest SHA-256 |
|---|---|---|---|
| `fact_commission` | PASS; rowcount 3/3; dup 0; null 0; row_diff 0; key_preservation 3/3; base_premium cents 2880000=2880000; commission_amt cents 7000=7000; fact_covers_ledger 3/3; idempotency performed+pass | PASS with identical values; rerun `cdw-20260901T233610Z-b83ff70e` SUCCEEDED; quarantine 0 | `e525530e7eeea27b2f3a671109a301e09732de2942df7477f68910002c7ed0f9` |
| `mv_agent_commission_summary` | PASS; rowcount 3/3; dup 0; null 0; row_diff 0; total_commission cents 7000=7000; idempotency performed+pass | PASS with identical values | `3028c5bf2efd96efcef22d5bee13a53a33153ef1732787b9ffa8ca4a4dfe7101` |

Parent evidence is preserved beside this brief:

- `.migration/recon/wave2/fact_commission.parent.recon.json`
- `.migration/recon/wave2/fact_commission.parent.summary.md`
- `.migration/recon/wave2/mv_agent_commission_summary.parent.recon.json`
- `.migration/recon/wave2/mv_agent_commission_summary.parent.summary.md`

## Decisions and dependencies

- DEC-018 records per-`(run_id, unit)` quarantine cleanup and one
  `run_log` row per attempt, with status distinguishing failed and retried
  attempts.
- DEC-015 cross-table atomicity remains unverified until parallel run.
- D3-1 is IMPLEMENTED: T0 refreshes the feed with `cdw_baseline.py load-feed`;
  post-cutover extraction is customer-run at STOP E.
- D4-1 is IMPLEMENTED: the gold report surface landed; the consumer evidence
  gap remains a STOP E item.
- D5-1 is IMPLEMENTED: job `939320833644147` is PAUSED with monthly cron
  `0 0 6 1 * ? UTC` and manual trigger.

## Review findings and implications

Two review rounds and three threads were resolved:

1. The `dim_period` task now honors the `period_month` filter.
2. A retried attempt clears its own quarantine rows first.
3. SQL splitting no longer breaks the `concat_ws('; ', …)` literal; the one
   failed full run led to a quote-aware splitter rule.

The quote-aware splitter and retry-idempotence rules are now part of the
Oracle-to-Databricks skill guidance.

## SKILL FEEDBACK harvested (3 items)

1. Quote-aware SQL splitting → `oracle-plsql` skill.
2. Explicit `dropped_join_rows` check id → recon tooling in this change.
3. One run-log row per retry attempt → DEC-018 and the skill.

## Unproven paths

Live legacy comparison remains DEGRADED under D10-1; the customer’s
in-perimeter comparison is a STOP E entry criterion. Cross-table atomicity
(DEC-015) remains open until parallel run. The `dropped_join_rows > 0` branch
was code-reviewed only, and the period-month-filtered incremental path was
code-reviewed only; all completed runs processed the full three-row estate.

## Cost

Child: ≈8.5 ACU; five full job runs: ≈5.4 serverless wh-min. Parent recon
window: ≈1 wh-min; parent orchestration ACU: parent: this session.
