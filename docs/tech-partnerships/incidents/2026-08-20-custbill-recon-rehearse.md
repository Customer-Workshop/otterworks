# Incident: CUSTBILL history reconciliation failure — ns `rehearse` (2026-08-20)

## Summary

The scheduled Databricks recon job `ow_tp_billing_history_recon_rehearse` failed
(job 878053742684156, run 683674105940596:
https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/878053742684156/runs/683674105940596).
Twelve newly arrived 2025 monthly CUSTBILL drops had landed in the volume and were
registered in the expectations table, but the migrated target was never backfilled,
so the gold aggregates went stale relative to the legacy-derived expectations.

## Failing checks (reproduced locally with `showcase.py --ns rehearse recon`)

```
checks: 57, failed: 9, anomalies expected/actual: 30/30, missing: 0, unexpected: 0
  FAIL annual_total/2025/EUR/01 expected=134|65183169 actual=0|0
  FAIL annual_total/2025/EUR/02 expected=25|12542424 actual=0|0
  FAIL annual_total/2025/GBP/01 expected=138|68261644 actual=0|0
  FAIL annual_total/2025/GBP/02 expected=33|18477344 actual=0|0
  FAIL annual_total/2025/USD/01 expected=123|64493857 actual=0|0
  FAIL annual_total/2025/USD/02 expected=23|12100218 actual=0|0
  FAIL file_count/2025 expected=12 actual=0
  FAIL grand_total/all_years expected=3332|1675716652 actual=2856|1434657996
  FAIL quarantine_count/2025 expected=4 actual=0
```

The full failing report is committed alongside this note as
`custbill_history_backfill-rehearse.recon.failed-20260820.json`.

## Root cause (evidence-based)

- Landing volume `/Volumes/ow_tp/bronze/landing/rehearse/history/2025/` contained all
  12 monthly drops `CUSTBILL_REHEARSE_202501.dat` … `CUSTBILL_REHEARSE_202512.dat`.
- Expectations table `ow_tp.ops.history_expectations_rehearse` covered 2019–2025
  (42 rows, 6 per source year, including 2025).
- Bronze `ow_tp.bronze.custbill_history_raw_rehearse` stopped at 2024:
  6 years × 12 files, 3024 rows, `max(source_year)=2024`.

Classic "new history arrived, target stale": pure data catch-up, no pipeline logic
defect. No repo code needed changing.

## Remediation

Ran the standard backfill (bronze → silver + quarantine → gold), no table hand-edits:

```
python3 scripts/tp_dbx/showcase.py --ns rehearse backfill
# bronze_rows 3024 → 3528, files 72 → 84, silver 2856 → 3332,
# quarantined 30 → 35, last_year 2024 → 2025
```

Regenerated the legacy-derived expectations manifest to cover the new drop range:
`make legacy-etl-gen-history NS=rehearse START_YEAR=2019 END_YEAR=2025`
(84 files, 3360 records, 35 expected anomalies — deterministic generator).

## Proof

- Recon green: `checks: 57, failed: 0, anomalies expected/actual: 35/35, missing: 0,
  unexpected: 0` — report committed at
  `docs/tech-partnerships/recon/custbill_history_backfill-rehearse.recon.json`
  (`run_mode: live`, `values_recomputed_from_target: true`, `idempotency_rerun:
  performed=true result=pass`).
- Delta time travel on `ow_tp.gold.custbill_annual_rehearse`:

  Before the fix (stale at 2024):

  ```
  totals AS OF v2: {'record_count': '2856', 'total_amount_cents': '1434657996'}
  totals AS OF v3: {'record_count': '2856', 'total_amount_cents': '1434657996'}
  ```

  After the backfill (2025 caught up):

  ```
  v5 2026-08-20T04:20:40.000Z WRITE
  v4 2026-08-20T04:20:22.000Z WRITE
  totals AS OF v4: {'record_count': '3332', 'total_amount_cents': '1675716652'}
  totals AS OF v5: {'record_count': '3332', 'total_amount_cents': '1675716652'}
  ```

- Recon job re-triggered and green:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/runs/341953539891524
  (`result: SUCCESS`, task `recon_check: SUCCESS`, `notify_devin: EXCLUDED`).
- Job schedule remains PAUSED.
