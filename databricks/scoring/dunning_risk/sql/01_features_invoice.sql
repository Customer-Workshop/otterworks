-- ow_tp_dunning_risk task 1/6: per-invoice dunning features.
--
-- One row per row of ow_tp.silver.invoice_header. Everything here is a fact read off the
-- migrated Delta history; no scoring, no thresholds, no judgement.
--
-- Two rules this file obeys, both from the pre-PR self-check:
--
--   * a feature that has no source in the migrated estate is NULL and carries a reason in
--     its `*_cov` column. It is never defaulted to zero, because zero reads as "no prior
--     overdue invoices" when the truth is "nobody migrated the evidence";
--   * the point-in-time features look only at strictly earlier invoices of the same
--     account, so a row never sees its own outcome.
--
-- Aging is measured from `invoice_dt_parsed` (the migrated INVOICES.ISSUED_AT), not from
-- `due_dt_parsed`, because that is what the legacy dunning job measures: pkg_dunning's
-- fn_overdue_accounts computes `TRUNC(p_as_of) - TRUNC(CAST(i.issued_at AS DATE))` and
-- sp_suspend_overdue compares `issued_at <= p_as_of - 14`. The due date is carried anyway,
-- with `due_before_invoice_dt` flagging the 9,409 migrated invoices whose due date precedes
-- their invoice date. That is legacy data as migrated; this file reports it, it does not
-- repair it.
--
-- `prior_overdue_rate` reads the *current* status of earlier invoices. No invoice status
-- history was migrated, so "was this invoice overdue at the time" cannot be answered. This
-- is the leakage caveat on the backtest and is stated there too.
--
-- The `as_of` job parameter is the clock. Left empty (the default) it resolves to the newest
-- invoice date in the migrated history, which is that extract's own "today". The legacy job
-- takes `p_as_of` and is handed SYSDATE against a live database; against a frozen extract the
-- honest equivalent of SYSDATE is the extract's high-water mark, not the wall clock. Running
-- with the wall clock instead makes every open invoice older than the oldest aging band, and
-- the queue collapses to a single bucket. Pass an explicit date to override, which is what a
-- live Lakebase-fed rebuild should do once the OLTP side is the source.

CREATE OR REPLACE TABLE ow_tp.silver.dunning_risk_features_invoice AS
WITH asof AS (
  SELECT coalesce(try_to_date(:as_of), max(CAST(invoice_dt_parsed AS DATE))) AS as_of_dt
  FROM ow_tp.silver.invoice_header
),
base AS (
  SELECT
    h.invoice_id,
    h.invoice_no,
    h.cust_id,
    h.tenant_id,
    h.status_cd,
    h.total_amt,
    h.invoice_dt_parsed,
    h.due_dt_parsed,
    c.cust_id                        AS master_cust_id,
    c.credit_hold_yn,
    c.vip_yn,
    c.dunning_exempt_yn,
    c.segment_cd,
    CAST(c.credit_limit_amt AS DECIMAL(14, 2)) AS credit_limit_amt,
    CAST(c.past_due_amt AS DECIMAL(14, 2))     AS past_due_amt,
    CAST(c.cur_bal_amt AS DECIMAL(14, 2))      AS cur_bal_amt
  FROM ow_tp.silver.invoice_header h
  LEFT JOIN ow_tp.bronze.customer_master c
         ON c.cust_id = h.cust_id
),
windowed AS (
  SELECT
    b.*,
    -- strictly earlier invoices of the same account, oldest first; invoice_id breaks ties
    -- so the frame is deterministic across reruns.
    count(*) OVER w                                        AS prior_invoice_cnt,
    count(CASE WHEN status_cd IN (30, 40) THEN 1 END) OVER w   AS prior_closed_cnt,
    count(CASE WHEN status_cd = 40 THEN 1 END) OVER w          AS prior_overdue_cnt,
    avg(CASE WHEN status_cd IN (30, 40) THEN total_amt END) OVER w AS prior_mean_amt,
    min(invoice_dt_parsed) OVER (PARTITION BY cust_id)     AS first_invoice_dt
  FROM base b
  WINDOW w AS (
    PARTITION BY cust_id
    ORDER BY invoice_dt_parsed, invoice_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  )
)
SELECT
  invoice_id,
  invoice_no,
  cust_id,
  tenant_id,
  status_cd,
  status_cd = 40                                        AS is_overdue,
  status_cd IN (20, 40)                                 AS is_open,
  -- the legacy nightly job dunns status 40 and nothing else (pkg_dunning.sp_schedule_dunning)
  status_cd = 40                                        AS legacy_dunning_eligible,
  CAST(total_amt AS DECIMAL(14, 2))                     AS total_amt,
  invoice_dt_parsed,
  due_dt_parsed,
  due_dt_parsed IS NOT NULL
    AND due_dt_parsed < invoice_dt_parsed                AS due_before_invoice_dt,
  CAST(datediff(a.as_of_dt, CAST(invoice_dt_parsed AS DATE)) AS INT) AS age_days,

  -- payment lateness history (proxy). The migrated master carries no LAST_PAYMENT_DT and no
  -- payment table came across, so lateness is inferred from how earlier invoices of the same
  -- account ended up. Below three closed invoices the rate is noise, so it is NULL, not 0.
  prior_invoice_cnt,
  prior_closed_cnt,
  prior_overdue_cnt,
  CASE WHEN prior_closed_cnt >= 3
       THEN CAST(prior_overdue_cnt AS DECIMAL(9, 6)) / prior_closed_cnt END AS prior_overdue_rate,
  CASE WHEN prior_closed_cnt >= 3 THEN 'ok'
       WHEN prior_closed_cnt > 0  THEN 'insufficient_history'
       ELSE 'no_prior_closed_invoices' END              AS prior_overdue_rate_cov,

  -- invoice size against the account's own norm, running mean of its earlier closed invoices
  CAST(prior_mean_amt AS DECIMAL(14, 2))                AS prior_mean_amt,
  CASE WHEN prior_closed_cnt >= 3 AND prior_mean_amt > 0
       THEN CAST(total_amt / prior_mean_amt AS DECIMAL(9, 4)) END AS amt_vs_account_norm,
  CASE WHEN prior_closed_cnt >= 3 AND prior_mean_amt > 0 THEN 'ok'
       ELSE 'insufficient_history' END                  AS amt_vs_account_norm_cov,

  -- credit posture, straight off the migrated billing master
  credit_hold_yn,
  vip_yn,
  dunning_exempt_yn,
  segment_cd,
  credit_limit_amt,
  past_due_amt,
  cur_bal_amt,
  CASE WHEN credit_limit_amt > 0
       THEN CAST(past_due_amt / credit_limit_amt AS DECIMAL(9, 4)) END AS past_due_vs_limit,
  CASE WHEN master_cust_id IS NULL     THEN 'no_master_row'
       WHEN credit_limit_amt IS NULL   THEN 'null_credit_limit'
       WHEN credit_limit_amt <= 0      THEN 'zero_credit_limit'
       ELSE 'ok' END                                    AS past_due_vs_limit_cov,

  -- tenure. SIGNUP_DT is a DD-MON-YY string with a two-digit year, so its century is
  -- ambiguous and it is not used; tenure is measured from the account's first migrated
  -- invoice, which is unambiguous.
  first_invoice_dt,
  CAST(datediff(a.as_of_dt, CAST(first_invoice_dt AS DATE)) AS INT) AS tenure_days,
  CASE WHEN first_invoice_dt IS NULL THEN 'no_invoice_history' ELSE 'ok' END AS tenure_days_cov,

  -- Requested features that the migrated estate cannot supply for this population. They are
  -- declared as NULL columns carrying the reason, so the score's inputs stay visible and so
  -- that reconciling the two key spaces later fills them in without reshaping the score.
  --
  -- dunning_attempts, credit_notes, plans and subscriptions reached Lakebase but not Delta,
  -- and every one of them is keyed on billing.tenants.id. The invoice history is keyed on
  -- customer_master.tenant_id. Those two sets do not intersect: 50 tenant ids on the invoice
  -- side, 69 on the tenant side, 0 in common. usage_events did reach Delta and is keyed the
  -- same way, so it is disjoint from the invoices for the same reason. See README.md.
  CAST(NULL AS INT)            AS prior_dunning_attempts,
  CAST(NULL AS INT)            AS prior_dunning_sent,
  'source_in_lakebase_only'    AS prior_dunning_cov,
  CAST(NULL AS DECIMAL(14, 2)) AS open_credit_note_amt,
  'source_in_lakebase_only'    AS credit_note_cov,
  CAST(NULL AS SMALLINT)       AS plan_tier_cd,
  'source_in_lakebase_only'    AS plan_cov,
  CAST(NULL AS DECIMAL(9, 4))  AS usage_trend_ratio,
  'tenant_key_space_disjoint'  AS usage_trend_cov,

  a.as_of_dt,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)            AS built_at
FROM windowed
CROSS JOIN asof a
