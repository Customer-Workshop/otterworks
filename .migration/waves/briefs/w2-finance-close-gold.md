UNIT finance_close_gold (wave 2, serial, width 1). Gold finance table and the one AI/BI dashboard.
1. ow_tp.mig_20260927b_gold.finance_close_detail: one row per invoice the close covers, from
   ow_tp.mig_20260927b_silver.custbill_records joined back to ow_tp.mig_20260927b_bronze.invoice_header
   (invoice_id, cust_id, tenant_id, invoice_dt, total_amt, batch_no, status_cd, plus cust_no, period_end,
   currency, rec_type). ow_tp.mig_20260927b_gold.finance_close: SUM(total_amt) and COUNT(*) grouped by currency
   and rec_type, with ns = 'demo' and close_run_at: the same computation the legacy finance close performs
   (GET /api/reports/finance?ns=demo over the parsed CUSTBILL records). Both as tables built by a small DAB
   (databricks/mig_20260927b/finance_close/, target mig_20260927b, job ow_tp_20260927b_finance_close, schedule
   PAUSED, run once manually).
2. Dashboard ow_tp_20260927b_finance_close_dashboard (databricks:databricks-aibi-dashboards; test every query on warehouse
   565cd2fd713738c4 first): one page with the close total by currency / rec_type from finance_close, the detail
   row count, and the file sha256 from ow_tp.mig_20260927b_silver.custbill_file_manifest. JSON committed under
   databricks/mig_20260927b/dashboards/. Report the dashboard URL.
3. Legacy side: the legacy finance close total for NS=demo from the legacy chain (the finance report endpoint or
   its CSV, run locally over the legacy .dat, Oracle read-only), recorded in
   .migration/recon/finance_close_gold/close_total.json side by side with the gold row.
4. Gates: w2-detail-parity (row_parity, depth full, PASS of finance_close_detail vs Oracle INVOICE_HEADER scoped
   by the mapping's root_where), w2-close-total (publish_leg: gold total == SUM(detail) == legacy close total ==
   the dbx-recon Tier-2 aggregate_sum(TOTAL_AMT) of the detail run, all four values printed), w2-dashboard
   (structural: dashboard published, every query runs on the warehouse, URL recorded).
Write targets: ow_tp.mig_20260927b_gold.finance_close_detail, ow_tp.mig_20260927b_gold.finance_close, dashboard
ow_tp_20260927b_finance_close_dashboard, job ow_tp_20260927b_finance_close.
