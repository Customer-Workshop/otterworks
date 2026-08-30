"""gold_finance: the wave 5 unit of the OW_BILLING → Databricks run, and the last one.

`etl/legacy-extra/jobs/finance_excel_report.pl` on Delta — `ow_tp.gold.finance_monthly`,
`ow_tp.gold.finance_report_export`, `ow_tp.gold.quarantine_gold_finance` and the volume export — plus
the live reconciliation that measures the port against the Perl script actually executed over the
same inputs, against the CUSTBILL population `bronze_custbill` landed, and against the Delta targets.

The population is stated once here because it decides every figure: the report reads
`$ROOT/parsed/CUSTBILL*.psv`, the denormalised CUSTBILL stream, landed as
`ow_tp.bronze.custbill_records`. It is not `ow_tp.silver.invoices`. The normalised figures are
published beside the CUSTBILL figures in the recon report as a declared disagreement and are
reconciled to nothing.
"""
