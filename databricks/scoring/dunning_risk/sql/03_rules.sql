-- ow_tp_dunning_risk task 3/6: the model.
--
-- This table *is* the model. It is not documentation of the model; 04 and 05 read the
-- points out of it and sum them, so the numbers printed by
--
--   SELECT rule_id, condition, points, rationale FROM ow_tp.gold.dunning_risk_rules ORDER BY seq
--
-- are by construction the numbers that produced every score. Changing a weight is a change
-- to this file and nothing else.
--
-- Where the thresholds come from, and where they do not:
--
--   * the aging steps are multiples of 14 days. 14 is the only dunning interval the legacy
--     estate actually declares: pkg_dunning.sp_suspend_overdue suspends a tenant whose
--     invoice was issued `p_as_of - 14` or earlier. 28/56/84 are two, four and six of that
--     step. They were not fitted, and they could not be: see ow_tp.gold.dunning_risk_backtest;
--   * PRIOR_OVERDUE, SIZE, EXPOSURE and CREDIT_HOLD are collections policy written down.
--     Their weights say which signal an analyst should look at first when two accounts are
--     the same age. They are an ordering, not a probability;
--   * VIP and DUNNING_EXEMPT are suppressors that exist in the migrated billing master and
--     are honoured rather than scored around.
--
-- The maximum reachable score is 30 + 20 + 15 + 15 + 20 = 100 and scores are clamped to
-- [0, 100] after the VIP suppressor.

CREATE OR REPLACE TABLE ow_tp.gold.dunning_risk_rules AS
SELECT
  CAST(seq AS INT)              AS seq,
  rule_id,
  signal,
  feature,
  condition,
  CAST(points AS INT)           AS points,
  rationale,
  CAST(current_timestamp() AS TIMESTAMP_NTZ) AS built_at
FROM VALUES
  (10, 'AGE_84_PLUS',         'invoice age',
       'age_days',
       'age_days >= 84', 30,
       'Six legacy suspension intervals unpaid. The oldest bucket, so age alone can reach HIGH but never CRITICAL on its own.'),
  (11, 'AGE_56_83',           'invoice age',
       'age_days',
       'age_days BETWEEN 56 AND 83', 22,
       'Four legacy suspension intervals unpaid.'),
  (12, 'AGE_28_55',           'invoice age',
       'age_days',
       'age_days BETWEEN 28 AND 55', 14,
       'Two legacy suspension intervals unpaid.'),
  (13, 'AGE_14_27',           'invoice age',
       'age_days',
       'age_days BETWEEN 14 AND 27', 6,
       'Past the one interval the legacy estate declares (pkg_dunning.sp_suspend_overdue, p_as_of - 14).'),

  (20, 'PRIOR_OVERDUE_HIGH',  'payment lateness history',
       'prior_overdue_rate',
       'prior_overdue_rate >= 0.50', 20,
       'Half or more of this account''s earlier closed invoices ended overdue. Proxy: no payment dates were migrated, so "ended overdue" is the only lateness evidence that exists.'),
  (21, 'PRIOR_OVERDUE_MED',   'payment lateness history',
       'prior_overdue_rate',
       'prior_overdue_rate >= 0.25 AND prior_overdue_rate < 0.50', 10,
       'A quarter to a half of earlier closed invoices ended overdue.'),

  (30, 'SIZE_3X_NORM',        'invoice size vs account norm',
       'amt_vs_account_norm',
       'amt_vs_account_norm >= 3.0', 15,
       'Three times this account''s own running mean. Unusually large invoices are the ones queried and deferred, and they carry the most exposure.'),
  (31, 'SIZE_1_5X_NORM',      'invoice size vs account norm',
       'amt_vs_account_norm',
       'amt_vs_account_norm >= 1.5 AND amt_vs_account_norm < 3.0', 8,
       'Half again this account''s own running mean.'),

  (40, 'EXPOSURE_OVER_LIMIT', 'credit exposure',
       'past_due_vs_limit',
       'past_due_vs_limit >= 1.0', 15,
       'Past-due balance has reached or passed the credit limit the billing master records.'),
  (41, 'EXPOSURE_HALF_LIMIT', 'credit exposure',
       'past_due_vs_limit',
       'past_due_vs_limit >= 0.5 AND past_due_vs_limit < 1.0', 8,
       'Past-due balance is at least half the credit limit.'),

  (50, 'CREDIT_HOLD',         'declared credit posture',
       'credit_hold_yn',
       'credit_hold_yn = ''Y''', 20,
       'Someone has already put this account on credit hold. It is a human judgement already made, so it is weighted like the strongest history signal.'),

  (60, 'VIP_SUPPRESS',        'suppressor',
       'vip_yn',
       'vip_yn = ''Y''', -10,
       'VIP accounts are handled by an account manager. Lower the queue position; never below 0.'),
  (61, 'DUNNING_EXEMPT',      'suppressor',
       'dunning_exempt_yn',
       'dunning_exempt_yn = ''Y''', 0,
       'Contractually exempt from dunning. Forces score 0 and band EXEMPT regardless of every other rule.')
AS t(seq, rule_id, signal, feature, condition, points, rationale)
