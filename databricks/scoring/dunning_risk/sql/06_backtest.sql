-- ow_tp_dunning_risk task 6/6: the backtest, including the parts that failed.
--
-- What is being tested, and what cannot be.
--
-- The label is `status_cd = 40` on a closed invoice: of the invoices that reached a terminal
-- state, which ones ended overdue. That is the closest thing to a dunning outcome the
-- migrated estate holds. The real outcome (did the dunning attempt recover the money) lives
-- in DUNNING_ATTEMPTS, which reached Lakebase with one row, on a tenant key space that does
-- not intersect the invoice history. So the honest statement is: the score was not
-- backtested against dunning outcomes, it was backtested against the overdue label.
--
-- The aging rules (AGE_*) are excluded from the backtested score on purpose. Days-since-issue
-- and "ended overdue" are the same event observed twice; including aging would produce a
-- large AUC that measures nothing. Aging is collections policy carried over from
-- pkg_dunning, not a prediction, and it is not claimed as one. What is tested here is
-- whether the other four signals order accounts better than chance.
--
-- Two leakage caveats that make these numbers optimistic, not pessimistic:
--
--   * `prior_overdue_rate` reads the *current* status of earlier invoices, because no
--     invoice status history was migrated;
--   * `credit_hold_yn`, `past_due_amt` and `credit_limit_amt` are today's values on the
--     billing master, not their values at invoice time. An account put on hold *because* it
--     went overdue looks, here, like an account that was on hold first.
--
-- Even with both caveats pointing the same way, the result is that these signals do not
-- discriminate on this data. That is the finding, and it is published rather than buried.

CREATE OR REPLACE TABLE ow_tp.gold.dunning_risk_backtest AS
WITH closed AS (
  SELECT
    f.invoice_id,
    f.invoice_dt_parsed,
    CASE WHEN f.status_cd = 40 THEN 1 ELSE 0 END AS y,
    year(f.invoice_dt_parsed) >= 2021             AS in_holdout,
    filter(array(
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
      CASE WHEN f.vip_yn = 'Y' THEN 'VIP_SUPPRESS' END
    ), x -> x IS NOT NULL) AS reason_codes,
    f.prior_overdue_rate,
    f.amt_vs_account_norm,
    f.past_due_vs_limit
  FROM ow_tp.silver.dunning_risk_features_invoice f
  WHERE f.status_cd IN (30, 40)
    AND f.invoice_dt_parsed IS NOT NULL
),
pts AS (
  SELECT e.invoice_id, coalesce(sum(r.points), 0) AS raw_points
  FROM (SELECT invoice_id, explode_outer(reason_codes) AS code FROM closed) e
  LEFT JOIN ow_tp.gold.dunning_risk_rules r ON r.rule_id = e.code
  GROUP BY e.invoice_id
),
scored AS (
  SELECT c.*, greatest(0, least(100, p.raw_points)) AS score,
         CASE WHEN greatest(0, least(100, p.raw_points)) >= 60 THEN 'CRITICAL'
              WHEN greatest(0, least(100, p.raw_points)) >= 40 THEN 'HIGH'
              WHEN greatest(0, least(100, p.raw_points)) >= 20 THEN 'MEDIUM'
              ELSE 'LOW' END AS band
  FROM closed c JOIN pts p ON p.invoice_id = c.invoice_id
),
-- Mann-Whitney AUC with mid-ranks for ties, computed per population.
ranked AS (
  SELECT population, y,
         rank() OVER (PARTITION BY population ORDER BY score)
           + (count(*) OVER (PARTITION BY population, score) - 1) / 2.0 AS avg_rank
  FROM (SELECT 'closed_all' AS population, y, score FROM scored
        UNION ALL
        SELECT 'closed_2021_plus', y, score FROM scored WHERE in_holdout)
),
auc AS (
  SELECT population,
         sum(CASE WHEN y = 1 THEN 1 ELSE 0 END) AS n_pos,
         sum(CASE WHEN y = 0 THEN 1 ELSE 0 END) AS n_neg,
         (sum(CASE WHEN y = 1 THEN avg_rank ELSE 0 END)
            - sum(CASE WHEN y = 1 THEN 1 ELSE 0 END)
              * (sum(CASE WHEN y = 1 THEN 1 ELSE 0 END) + 1) / 2.0)
         / (sum(CASE WHEN y = 1 THEN 1 ELSE 0 END)
            * sum(CASE WHEN y = 0 THEN 1 ELSE 0 END)) AS auc
  FROM ranked GROUP BY population
)

SELECT 'baseline' AS metric_group, 'overdue_rate' AS metric, 'closed_all' AS population,
       count(*) AS n, CAST(avg(y) AS DECIMAL(9, 6)) AS value,
       'share of terminal invoices that ended status 40' AS note
FROM scored
UNION ALL
SELECT 'baseline', 'overdue_rate', 'closed_2021_plus',
       count(*), CAST(avg(y) AS DECIMAL(9, 6)),
       'share of terminal invoices that ended status 40'
FROM scored WHERE in_holdout

UNION ALL
SELECT 'discrimination', 'auc', population, n_pos + n_neg, CAST(auc AS DECIMAL(9, 6)),
       'AUC of the non-aging rules against the overdue label. 0.5 is a coin toss.'
FROM auc

UNION ALL
SELECT 'band_outcome', band, 'closed_all', count(*), CAST(avg(y) AS DECIMAL(9, 6)),
       'observed overdue rate inside the band; a working score makes this rise with the band'
FROM scored GROUP BY band
UNION ALL
SELECT 'band_outcome', band, 'closed_2021_plus', count(*), CAST(avg(y) AS DECIMAL(9, 6)),
       'observed overdue rate inside the band; a working score makes this rise with the band'
FROM scored WHERE in_holdout GROUP BY band

UNION ALL
SELECT 'rule_lift', r.rule_id, 'closed_2021_plus',
       count(CASE WHEN array_contains(s.reason_codes, r.rule_id) THEN 1 END),
       CAST(avg(CASE WHEN array_contains(s.reason_codes, r.rule_id) THEN s.y END)
            AS DECIMAL(9, 6)),
       'overdue rate among the invoices this rule fired on; compare with the baseline row'
FROM scored s CROSS JOIN ow_tp.gold.dunning_risk_rules r
WHERE s.in_holdout AND r.signal <> 'invoice age' AND r.rule_id <> 'DUNNING_EXEMPT'
GROUP BY r.rule_id

UNION ALL
SELECT 'coverage', 'prior_overdue_rate', 'closed_all',
       count(CASE WHEN prior_overdue_rate IS NULL THEN 1 END),
       CAST(avg(CASE WHEN prior_overdue_rate IS NULL THEN 1.0 ELSE 0.0 END) AS DECIMAL(9, 6)),
       'rows where the signal could not be evaluated at all'
FROM scored
UNION ALL
SELECT 'coverage', 'amt_vs_account_norm', 'closed_all',
       count(CASE WHEN amt_vs_account_norm IS NULL THEN 1 END),
       CAST(avg(CASE WHEN amt_vs_account_norm IS NULL THEN 1.0 ELSE 0.0 END) AS DECIMAL(9, 6)),
       'rows where the signal could not be evaluated at all'
FROM scored
UNION ALL
SELECT 'coverage', 'past_due_vs_limit', 'closed_all',
       count(CASE WHEN past_due_vs_limit IS NULL THEN 1 END),
       CAST(avg(CASE WHEN past_due_vs_limit IS NULL THEN 1.0 ELSE 0.0 END) AS DECIMAL(9, 6)),
       'rows where the signal could not be evaluated at all'
FROM scored
UNION ALL
SELECT 'coverage', 'dunning_outcome_label', 'closed_all', 0, CAST(0 AS DECIMAL(9, 6)),
       'no dunning outcome was testable: DUNNING_ATTEMPTS is Lakebase-only and its tenant key space does not intersect the invoice history'
