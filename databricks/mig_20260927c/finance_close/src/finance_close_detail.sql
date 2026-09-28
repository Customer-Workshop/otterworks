-- finance_close_detail: one row per invoice the CUSTBILL close covers.
-- The silver custbill_records set is the parsed legacy feed (batch or admin tenant,
-- expectations applied); joining back to bronze invoice_header restores the
-- INVOICE_HEADER columns the row-parity recon compares against Oracle.
CREATE SCHEMA IF NOT EXISTS ow_tp.mig_20260927c_gold;

CREATE OR REPLACE TABLE ow_tp.mig_20260927c_gold.finance_close_detail AS
SELECT
  h.invoice_id,
  h.cust_id,
  h.tenant_id,
  h.invoice_dt,
  h.total_amt,
  h.batch_no,
  h.status_cd,
  s.cust_no,
  s.period_end,
  s.currency,
  s.record_type AS rec_type
FROM ow_tp.mig_20260927c_silver.custbill_records AS s
JOIN ow_tp.mig_20260927c_bronze.invoice_header AS h
  ON h.invoice_id = s.invoice_id;
