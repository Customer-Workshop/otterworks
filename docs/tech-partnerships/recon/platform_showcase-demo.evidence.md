# Platform showcase evidence — ns=demo (run tp-run/databricks-20260818T210550Z)

Artifacts created by the platform-showcase unit on the shared demo workspace.
Every schedule below was created PAUSED and re-verified PAUSED at the end of
the run. All objects are `ow_tp`-prefixed and scoped to `ns=demo`; conversion
tables were read (never written) from the `cnvorch` namespace slice.

## Declarative pipeline (expectations = quarantine policy)

- Pipeline `ow_tp_custbill_history_dlt_demo`:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/pipelines/81f75b4a-ad26-4980-a8c8-69f395537220
- Green update (manual trigger, serverless):
  https://dbc-8bc9474f-40ae.cloud.databricks.com/pipelines/81f75b4a-ad26-4980-a8c8-69f395537220/updates/3f0d3385-4d99-44f5-b1ec-5036ef32e979
- Expectations (`EXPECT ... ON VIOLATION DROP ROW`) dropped exactly the rows
  the harness quarantines; pipeline gold vs harness gold parity: match.

## Unity Catalog lineage (lineage API, no manual annotation)

- Resolves landing volume → bronze → silver (+ quarantine) → gold.
- Catalog Explorer lineage tab:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/explore/data/ow_tp/silver/custbill_history_demo?activeTab=lineage

## AI/BI dashboard `ow_tp_billing_migration_demo` (published, 2 pages)

- Published:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/dashboardsv3/01f19b4c3bba14e0ae05b8c9e2c21e70/published
- Page 1 (backfill) built unmodified by the harness (`CMD=dashboard`).
- Page 2 (conversion) built live by `scripts/tp_dbx/conversion_page.py` from
  the tables this run's conversion children actually produced (discovered via
  `SHOW TABLES`, all landed by the merged orchestration run in the `cnvorch`
  slice): `ow_tp.bronze.custbill_ingest_files_cnvorch`,
  `ow_tp.bronze.custbill_raw_cnvorch`, `ow_tp.silver.custbill_parsed_cnvorch`,
  `ow_tp.silver.custbill_parse_quarantine_cnvorch`,
  `ow_tp.gold.finance_billing_summary_cnvorch`,
  `ow_tp.gold.finance_report_delivery_cnvorch`.
- Legacy side of the finance parity table: deterministic legacy run
  (`gen_sample_data.pl` + `run_all.sh`, NS=cnvorch) landed as
  `ow_tp.ops.legacy_finance_report_demo`.
- Every page-2 dataset verified non-empty before publishing
  (cnv_summary=1, cnv_parity=5, cnv_parity_state=1, cnv_delivery=1,
  cnv_receipt=4 rows); finance parity delta all zeros (5/5 currency ×
  record-type rows to the cent).
- Receipt table maps each legacy script to its converted job and merged PR:
  `sftp_ingest_poll.ksh` → `ow_tp_ingest_cnvingest` (#1195),
  `parse_custbill_fixedwidth.sh` → `ow_tp_parse_cnvparse` (#1194),
  `finance_excel_report.pl` → `ow_tp_finance_cnvfinance` (#1196),
  `run_all.sh` → `ow_tp_orchestrate_cnvorch` (#1197).

## Recon alert (PAUSED)

- `ow_tp_recon_failed_demo`:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/sql/alerts/3887578863199005

## Recon job with Devin notifier (schedule PAUSED)

- Job `ow_tp_billing_history_recon_demo`:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/402112166843203
- Tasks: `recon_check` (raise_error on any failing check) →
  `notify_devin` (`run_if: AT_LEAST_ONE_FAILED`, POSTs job/run/namespace/base
  branch to the Devin automation webhook; shared secret read from secret scope
  `ow_tp`/`devin_webhook_secret`, never inlined).
- Green-path proof:
  https://dbc-8bc9474f-40ae.cloud.databricks.com/jobs/runs/197477330021785
  — `recon_check` SUCCESS, `notify_devin` EXCLUDED.
- Red-path rehearsal is intentionally NOT run against `ns=demo`; the parent
  owns the failure-loop rehearsal in a throwaway namespace.

## End-of-run state

- `make dbx-showcase CMD=status NS=demo`: bronze=3024 lines / 72 files,
  silver=2856, quarantined=30, gold_cents=1439098122, expectation_rows=36;
  job schedule PAUSED, alert PAUSED.
- Recon: 49 checks pass / 0 fail, anomalies 30/30 (unchanged from backfill).
