-- ow_tp.gold.fct_ar_open_invoice — open receivable per invoice, aged as of a date.
--
-- Open is the invoice header status: 20 issued and 40 overdue are open, 30 paid is closed,
-- 10 draft is not a receivable. The migrated estate has no payment or allocation table, so
-- there is no such thing as a partly paid invoice here: the open balance is the header's
-- total_amt in full, and the only way a balance leaves AR is the status flipping to 30.
-- That is a real limit of the source, not a modelling choice — see METRIC_DEFINITIONS.md.
--
-- Invoice lines are deliberately not used. 150,000 lines exist, but the line total ties to
-- the header total on 0 of 18,745 invoices with lines, and 37 lines point at an invoice_id
-- with no header at all. Summing lines would quietly restate the receivable, so the header
-- is the single authority for money and the line problems are recorded in
-- ow_tp.gold.dq_exceptions instead of being dropped.
--
-- Ageing is by days past due at as_of_date: 0 or less is not yet due, then 0-30, 31-60,
-- 61-90, 90+. An invoice whose due date is null or did not parse goes to the 'unknown'
-- bucket and stays in the total: an unparseable date must never make a balance vanish. The
-- silver layer parses the legacy 'DD-MON-YY' strings (both date columns parse for all
-- 18,750 rows today), and this statement re-checks the raw string rather than trusting it.
--
-- days_past_due is kept alongside the bucket so any other as-of date can be recomputed
-- without rebuilding the table, and the metric view ages the same rows against the current
-- date as well.
CREATE OR REPLACE TABLE ow_tp.gold.fct_ar_open_invoice
COMMENT 'Open receivable per invoice (status 20/40) with days past due and ageing bucket at as_of_date. Balance is the header total; the estate has no payment table, so there are no partial balances.'
AS
WITH params AS (
  -- as_of_date is a job parameter. Empty (the default) ages the ledger at its own latest
  -- invoice date rather than at today: the migrated history stops on 2025-12-28, so a
  -- default of current_date() would put every open invoice in 90+ and hide the shape of
  -- the book. A dated run is a parameter change, not an edit to this statement.
  -- Only an empty value defaults. A value that is present but not a date fails the run,
  -- rather than quietly ageing the book at the ledger's own latest date under a label
  -- saying otherwise.
  SELECT CASE
           WHEN NULLIF(:as_of_date, '') IS NULL
             THEN (SELECT MAX(CAST(invoice_dt_parsed AS DATE))
                     FROM ow_tp.silver.invoice_header WHERE status_cd IN (20, 40))
           WHEN TRY_CAST(:as_of_date AS DATE) IS NULL
             THEN raise_error(CONCAT('as_of_date is not a date: ', :as_of_date))
           ELSE CAST(:as_of_date AS DATE)
         END AS as_of_date
),
open_inv AS (
  SELECT
    h.invoice_id,
    h.invoice_no,
    h.tenant_id,
    h.cust_id,
    h.status_cd,
    CAST(h.total_amt AS DECIMAL(14,2))                     AS open_amount,
    h.invoice_dt,
    h.due_dt,
    CAST(h.invoice_dt_parsed AS TIMESTAMP_NTZ)             AS invoice_ts,
    -- silver parses these already; re-derive from the raw string so a silver column that
    -- silently went null is visible here as an unparseable date instead of a missing row.
    CAST(TRY_TO_TIMESTAMP(h.due_dt, 'dd-MMM-yy') AS TIMESTAMP_NTZ) AS due_ts,
    p.as_of_date
  FROM ow_tp.silver.invoice_header h
  CROSS JOIN params p
  WHERE h.status_cd IN (20, 40)
)
SELECT
  o.as_of_date,
  o.invoice_id,
  o.invoice_no,
  o.tenant_id,
  o.cust_id,
  c.cust_name,
  o.status_cd,
  st.code_desc                                   AS invoice_status,
  o.open_amount,
  o.invoice_ts,
  o.due_ts,
  o.due_dt                                       AS due_dt_raw,
  DATEDIFF(o.as_of_date, CAST(o.due_ts AS DATE)) AS days_past_due,
  CASE
    WHEN o.due_ts IS NULL THEN 'unknown'
    WHEN DATEDIFF(o.as_of_date, CAST(o.due_ts AS DATE)) <= 0  THEN 'not yet due'
    WHEN DATEDIFF(o.as_of_date, CAST(o.due_ts AS DATE)) <= 30 THEN '0-30'
    WHEN DATEDIFF(o.as_of_date, CAST(o.due_ts AS DATE)) <= 60 THEN '31-60'
    WHEN DATEDIFF(o.as_of_date, CAST(o.due_ts AS DATE)) <= 90 THEN '61-90'
    ELSE '90+'
  END                                            AS ageing_bucket,
  o.due_ts IS NULL                               AS dq_due_date_unparseable,
  o.due_ts IS NOT NULL AND o.invoice_ts IS NOT NULL
    AND o.due_ts < o.invoice_ts                  AS dq_due_before_invoice,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)     AS built_at
FROM open_inv o
LEFT JOIN ow_tp.bronze.codes st
       ON st.code_type = 'INV_STATUS' AND st.code_val = o.status_cd
-- The customer name comes from the customer master, one row per cust_id, and not from the
-- denormalised copy on invoice lines: an invoice with no lines would otherwise have no
-- name, and a customer renamed between invoices would be labelled by whichever of its line
-- copies sorted highest. Line copies that disagree with the master are recorded in
-- ow_tp.gold.dq_exceptions.
LEFT JOIN ow_tp.bronze.customer_master c
       ON c.cust_id = o.cust_id
