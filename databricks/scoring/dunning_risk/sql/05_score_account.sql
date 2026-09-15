-- ow_tp_dunning_risk task 5/6: the per-account score.
--
-- An account's score is the score of its worst open invoice. Not an average, which would let
-- a pile of fresh invoices hide one that is ninety days old, and not a re-scoring of the
-- account with different weights, which would give the estate two models to argue about.
-- One rule table, one arithmetic, two grains.
--
-- Accounts with no open invoice are still emitted, with a NULL score and band 'NO_OPEN_ITEMS'.
-- Dropping them would make "not at risk" and "not scored" the same absent row.

CREATE OR REPLACE TABLE ow_tp.gold.dunning_risk_account AS
WITH worst AS (
  SELECT
    cust_id,
    max_by(invoice_id,   risk_score) AS worst_invoice_id,
    max_by(risk_score,   risk_score) AS risk_score,
    max_by(risk_band,    risk_score) AS risk_band,
    max_by(reason_codes, risk_score) AS reason_codes,
    max_by(age_days,     risk_score) AS worst_invoice_age_days,
    max(CASE WHEN risk_band = 'EXEMPT' THEN 1 ELSE 0 END) AS any_exempt,
    count(*)                         AS scored_open_invoice_cnt
  FROM ow_tp.gold.dunning_risk_invoice
  GROUP BY cust_id
)
SELECT
  a.cust_id,
  a.tenant_id,
  a.segment_cd,
  a.open_invoice_cnt,
  a.dunnable_invoice_cnt,
  a.open_amt,
  a.oldest_open_age_days,
  a.lifetime_overdue_rate,
  a.open_vs_limit,
  a.credit_limit_amt,
  a.past_due_amt,
  a.credit_hold_yn,
  a.vip_yn,
  a.dunning_exempt_yn,
  a.tenure_days,
  w.worst_invoice_id,
  CAST(CASE WHEN w.any_exempt = 1 THEN 0 ELSE w.risk_score END AS INT) AS risk_score,
  CASE WHEN a.open_invoice_cnt = 0 THEN 'NO_OPEN_ITEMS'
       WHEN w.any_exempt = 1       THEN 'EXEMPT'
       ELSE w.risk_band END                                  AS risk_band,
  w.reason_codes,
  w.worst_invoice_age_days,
  coalesce(w.scored_open_invoice_cnt, 0)                     AS scored_open_invoice_cnt,
  filter(array(
    CASE WHEN a.lifetime_overdue_rate IS NULL
         THEN concat('payment lateness history: ', a.lifetime_overdue_rate_cov) END,
    CASE WHEN a.open_vs_limit IS NULL
         THEN concat('credit exposure: ', a.open_vs_limit_cov) END,
    concat('previous dunning attempts: ', a.prior_dunning_cov),
    concat('credit notes: ', a.credit_note_cov),
    concat('plan: ', a.plan_cov),
    concat('usage trend: ', a.usage_trend_cov)
  ), x -> x IS NOT NULL)                                     AS unscored_signals,
  a.as_of_dt,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)                 AS built_at
FROM ow_tp.silver.dunning_risk_features_account a
LEFT JOIN worst w ON w.cust_id = a.cust_id
