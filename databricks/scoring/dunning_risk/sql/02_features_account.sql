-- ow_tp_dunning_risk task 2/6: per-account dunning features.
--
-- The dunning process acts on a billing account, so the account grain is cust_id, not
-- tenant_id. tenant_id is carried because it is on every invoice, but it is not the unit of
-- action here and it is not the same key space as billing.tenants (see 01_features_invoice.sql).
--
-- Every account in ow_tp.bronze.customer_master gets a row, including the 17,419 with no
-- invoices at all, so "this account has no open exposure" is a stated fact rather than an
-- absent row. Counts over an empty set are genuinely 0 and are written as 0; ratios over an
-- empty set are NULL with a coverage reason.

-- The clock is not recomputed here: `as_of_dt` is read back off the per-invoice table so the
-- two grains can never disagree about what day it is.

CREATE OR REPLACE TABLE ow_tp.silver.dunning_risk_features_account AS
WITH asof AS (
  SELECT max(as_of_dt) AS as_of_dt FROM ow_tp.silver.dunning_risk_features_invoice
),
inv AS (
  SELECT
    cust_id,
    max(tenant_id)                                              AS tenant_id,
    count(*)                                                    AS invoice_cnt,
    count(CASE WHEN status_cd IN (30, 40) THEN 1 END)           AS closed_cnt,
    count(CASE WHEN status_cd = 40 THEN 1 END)                  AS overdue_cnt,
    count(CASE WHEN is_open THEN 1 END)                         AS open_invoice_cnt,
    count(CASE WHEN legacy_dunning_eligible THEN 1 END)         AS dunnable_invoice_cnt,
    CAST(coalesce(sum(CASE WHEN is_open THEN total_amt END), 0) AS DECIMAL(14, 2))
                                                                AS open_amt,
    max(CASE WHEN is_open THEN age_days END)                    AS oldest_open_age_days,
    min(invoice_dt_parsed)                                      AS first_invoice_dt,
    max(invoice_dt_parsed)                                      AS last_invoice_dt,
    count(CASE WHEN due_before_invoice_dt THEN 1 END)           AS due_before_invoice_cnt
  FROM ow_tp.silver.dunning_risk_features_invoice
  GROUP BY cust_id
)
SELECT
  c.cust_id,
  i.tenant_id,
  c.segment_cd,
  c.status_cd                                        AS account_status_cd,
  c.credit_hold_yn,
  c.vip_yn,
  c.dunning_exempt_yn,
  CAST(c.credit_limit_amt AS DECIMAL(14, 2))         AS credit_limit_amt,
  CAST(c.past_due_amt AS DECIMAL(14, 2))             AS past_due_amt,
  CAST(c.cur_bal_amt AS DECIMAL(14, 2))              AS cur_bal_amt,

  coalesce(i.invoice_cnt, 0)                         AS invoice_cnt,
  coalesce(i.closed_cnt, 0)                          AS closed_cnt,
  coalesce(i.overdue_cnt, 0)                         AS overdue_cnt,
  coalesce(i.open_invoice_cnt, 0)                    AS open_invoice_cnt,
  coalesce(i.dunnable_invoice_cnt, 0)                AS dunnable_invoice_cnt,
  coalesce(i.open_amt, CAST(0 AS DECIMAL(14, 2)))    AS open_amt,
  i.oldest_open_age_days,
  i.first_invoice_dt,
  i.last_invoice_dt,
  coalesce(i.due_before_invoice_cnt, 0)              AS due_before_invoice_cnt,

  -- lifetime lateness proxy, same three-invoice floor as the per-invoice feature
  CASE WHEN i.closed_cnt >= 3
       THEN CAST(i.overdue_cnt AS DECIMAL(9, 6)) / i.closed_cnt END AS lifetime_overdue_rate,
  CASE WHEN i.closed_cnt >= 3 THEN 'ok'
       WHEN coalesce(i.closed_cnt, 0) > 0 THEN 'insufficient_history'
       ELSE 'no_closed_invoices' END                 AS lifetime_overdue_rate_cov,

  CASE WHEN c.credit_limit_amt > 0
       THEN CAST(coalesce(i.open_amt, 0) / c.credit_limit_amt AS DECIMAL(9, 4)) END
                                                     AS open_vs_limit,
  CASE WHEN c.credit_limit_amt IS NULL THEN 'null_credit_limit'
       WHEN c.credit_limit_amt <= 0    THEN 'zero_credit_limit'
       ELSE 'ok' END                                 AS open_vs_limit_cov,

  CAST(datediff(x.as_of_dt, CAST(i.first_invoice_dt AS DATE)) AS INT) AS tenure_days,
  CASE WHEN i.first_invoice_dt IS NULL THEN 'no_invoice_history' ELSE 'ok' END  AS tenure_days_cov,

  CAST(NULL AS INT)            AS prior_dunning_attempts,
  'source_in_lakebase_only'    AS prior_dunning_cov,
  CAST(NULL AS DECIMAL(14, 2)) AS open_credit_note_amt,
  'source_in_lakebase_only'    AS credit_note_cov,
  CAST(NULL AS SMALLINT)       AS plan_tier_cd,
  'source_in_lakebase_only'    AS plan_cov,
  CAST(NULL AS DECIMAL(9, 4))  AS usage_trend_ratio,
  'tenant_key_space_disjoint'  AS usage_trend_cov,

  x.as_of_dt,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)         AS built_at
FROM ow_tp.bronze.customer_master c
CROSS JOIN asof x
LEFT JOIN inv i ON i.cust_id = c.cust_id
