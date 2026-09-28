-- finance_close: the legacy finance_excel_report.pl computation (total and count
-- of parsed CUSTBILL records by currency and record type) over finance_close_detail.
CREATE OR REPLACE TABLE ow_tp.mig_20260927c_gold.finance_close AS
SELECT
  :ns AS ns,
  currency,
  rec_type,
  SUM(total_amt) AS total_amt,
  COUNT(*) AS record_count,
  current_timestamp() AS close_run_at
FROM ow_tp.mig_20260927c_gold.finance_close_detail
GROUP BY currency, rec_type;
