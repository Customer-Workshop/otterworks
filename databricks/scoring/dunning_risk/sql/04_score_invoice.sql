-- ow_tp_dunning_risk task 4/6: the per-open-invoice score.
--
-- Scope is the open invoices only (status 20 issued, 40 overdue). A paid invoice has no
-- dunning decision left to make.
--
-- The points are not written here. Each row produces the list of rule_ids whose condition
-- it meets, the list is joined to ow_tp.gold.dunning_risk_rules, and the score is the sum.
-- That join is the reason the printed rule table cannot drift from the applied one.
--
-- A rule whose feature is NULL does not fire. It also does not default to 0 points quietly:
-- `unscored_signals` lists, per row, every signal that could not be evaluated and why, so a
-- low score on a thin account is distinguishable from a low score on a well-evidenced one.
--
-- This table decides nothing. It carries no action column, no suspend flag and no dunning
-- trigger. `legacy_dunning_eligible` restates what the existing nightly job already selects
-- (status 40); the score orders that queue, it does not extend it.

CREATE OR REPLACE TABLE ow_tp.gold.dunning_risk_invoice AS
WITH fired AS (
  SELECT
    f.*,
    filter(array(
      CASE WHEN f.age_days >= 84 THEN 'AGE_84_PLUS' END,
      CASE WHEN f.age_days BETWEEN 56 AND 83 THEN 'AGE_56_83' END,
      CASE WHEN f.age_days BETWEEN 28 AND 55 THEN 'AGE_28_55' END,
      CASE WHEN f.age_days BETWEEN 14 AND 27 THEN 'AGE_14_27' END,
      CASE WHEN f.prior_overdue_rate >= 0.50 THEN 'PRIOR_OVERDUE_HIGH' END,
      CASE WHEN f.prior_overdue_rate >= 0.25 AND f.prior_overdue_rate < 0.50
           THEN 'PRIOR_OVERDUE_MED' END,
      CASE WHEN f.amt_vs_account_norm >= 3.0 THEN 'SIZE_3X_NORM' END,
      CASE WHEN f.amt_vs_account_norm >= 1.5 AND f.amt_vs_account_norm < 3.0
           THEN 'SIZE_1_5X_NORM' END,
      CASE WHEN f.past_due_vs_limit >= 1.0 THEN 'EXPOSURE_OVER_LIMIT' END,
      CASE WHEN f.past_due_vs_limit >= 0.5 AND f.past_due_vs_limit < 1.0
           THEN 'EXPOSURE_HALF_LIMIT' END,
      CASE WHEN f.credit_hold_yn = 'Y' THEN 'CREDIT_HOLD' END,
      CASE WHEN f.vip_yn = 'Y' THEN 'VIP_SUPPRESS' END,
      CASE WHEN f.dunning_exempt_yn = 'Y' THEN 'DUNNING_EXEMPT' END
    ), x -> x IS NOT NULL) AS reason_codes,
    filter(array(
      CASE WHEN f.prior_overdue_rate IS NULL
           THEN concat('payment lateness history: ', f.prior_overdue_rate_cov) END,
      CASE WHEN f.amt_vs_account_norm IS NULL
           THEN concat('invoice size vs account norm: ', f.amt_vs_account_norm_cov) END,
      CASE WHEN f.past_due_vs_limit IS NULL
           THEN concat('credit exposure: ', f.past_due_vs_limit_cov) END,
      concat('previous dunning attempts: ', f.prior_dunning_cov),
      concat('credit notes: ', f.credit_note_cov),
      concat('plan: ', f.plan_cov),
      concat('usage trend: ', f.usage_trend_cov)
    ), x -> x IS NOT NULL) AS unscored_signals
  FROM ow_tp.silver.dunning_risk_features_invoice f
  WHERE f.is_open
),
scored AS (
  SELECT
    e.invoice_id,
    coalesce(sum(r.points), 0) AS raw_points
  FROM (SELECT invoice_id, explode_outer(reason_codes) AS code FROM fired) e
  LEFT JOIN ow_tp.gold.dunning_risk_rules r ON r.rule_id = e.code
  GROUP BY e.invoice_id
)
SELECT
  f.invoice_id,
  f.invoice_no,
  f.cust_id,
  f.tenant_id,
  f.status_cd,
  f.legacy_dunning_eligible,
  f.total_amt,
  f.invoice_dt_parsed,
  f.due_dt_parsed,
  f.due_before_invoice_dt,
  f.age_days,
  CAST(CASE WHEN array_contains(f.reason_codes, 'DUNNING_EXEMPT') THEN 0
            ELSE greatest(0, least(100, s.raw_points)) END AS INT) AS risk_score,
  CASE WHEN array_contains(f.reason_codes, 'DUNNING_EXEMPT') THEN 'EXEMPT'
       WHEN greatest(0, least(100, s.raw_points)) >= 60 THEN 'CRITICAL'
       WHEN greatest(0, least(100, s.raw_points)) >= 40 THEN 'HIGH'
       WHEN greatest(0, least(100, s.raw_points)) >= 20 THEN 'MEDIUM'
       ELSE 'LOW' END                                            AS risk_band,
  f.reason_codes,
  f.unscored_signals,
  size(f.unscored_signals)                                       AS unscored_signal_cnt,
  f.prior_overdue_rate,
  f.amt_vs_account_norm,
  f.past_due_vs_limit,
  f.credit_hold_yn,
  f.vip_yn,
  f.dunning_exempt_yn,
  f.tenure_days,
  f.as_of_dt,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)                     AS built_at
FROM fired f
JOIN scored s ON s.invoice_id = f.invoice_id
