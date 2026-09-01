-- fact_commission loader: initialise from the FACT_COMMISSION baseline, guard
-- feed integrity, quarantine dropped inner-join rows, then apply the legacy MERGE.

INSERT INTO ow_tp.silver.fact_commission_cdw (fact_id, agent_key, product_key, period_key, policy_id, split_pct, base_premium, commission_amt, loaded_at)
SELECT fact_id, agent_key, product_key, period_key, policy_id, split_pct, base_premium, commission_amt, current_timestamp()
  FROM read_files('/Volumes/ow_tp/bronze/landing/cdw/baseline/FACT_COMMISSION.csv', format => 'csv', header => true,
       schema => 'fact_id BIGINT, agent_key BIGINT, product_key BIGINT, period_key BIGINT, policy_id BIGINT, split_pct DECIMAL(5,2), base_premium DECIMAL(12,2), commission_amt DECIMAL(12,2)',
       mode => 'FAILFAST');

SELECT assert_true(count_if(fact_id IS NULL OR agent_key IS NULL OR product_key IS NULL
                             OR period_key IS NULL OR policy_id IS NULL OR split_pct IS NULL
                             OR base_premium IS NULL OR commission_amt IS NULL) = 0,
                   'fact_commission baseline contains NULL in a NOT NULL column')
  FROM ow_tp.silver.fact_commission_cdw;

SELECT assert_true(count_if(ledger_id IS NULL OR policy_id IS NULL OR agent_id IS NULL
                            OR period_month IS NULL OR split_pct IS NULL
                            OR base_premium IS NULL OR commission_amt IS NULL) = 0,
                   'commission_ledger feed contains NULL in a NOT NULL fact_commission column')
  FROM ow_tp.bronze.commission_ledger_cdw
 WHERE __PERIOD_MONTH__ IS NULL OR period_month = __PERIOD_MONTH__;

SELECT assert_true(count(*) = 0,
                   'commission_ledger feed has duplicate (policy_id, agent_id, period_month) rows')
  FROM (
        SELECT policy_id, agent_id, period_month
          FROM ow_tp.bronze.commission_ledger_cdw
         WHERE __PERIOD_MONTH__ IS NULL OR period_month = __PERIOD_MONTH__
         GROUP BY 1, 2, 3
        HAVING count(*) > 1
       );

DELETE FROM ow_tp.ops.quarantine_cdw
 WHERE run_id = '__RUN_ID__'
   AND unit = 'fact_commission';

INSERT INTO ow_tp.ops.quarantine_cdw (run_id, unit, ledger_id, policy_id, agent_id, period_month, reason, quarantined_at)
SELECT '__RUN_ID__', 'fact_commission', cl.ledger_id, cl.policy_id, cl.agent_id, cl.period_month,
       concat_ws('; ',
         CASE WHEN po.policy_id IS NULL THEN 'no policy for policy_id' END,
         CASE WHEN da.agent_key IS NULL THEN 'no dim_agent for agent_id' END,
         CASE WHEN po.policy_id IS NOT NULL AND dp.product_key IS NULL THEN 'no dim_product for product_code' END,
         CASE WHEN dd.period_key IS NULL THEN 'no dim_period for period_month' END),
       current_timestamp()
  FROM ow_tp.bronze.commission_ledger_cdw cl
  LEFT JOIN ow_tp.bronze.policies_cdw po ON po.policy_id = cl.policy_id
  LEFT JOIN ow_tp.silver.dim_agent_cdw da ON da.agent_id = cl.agent_id
  LEFT JOIN ow_tp.silver.dim_product_cdw dp ON dp.product_code = po.product_code
  LEFT JOIN ow_tp.silver.dim_period_cdw dd ON dd.period_month = cl.period_month
 WHERE (__PERIOD_MONTH__ IS NULL OR cl.period_month = __PERIOD_MONTH__)
   AND (po.policy_id IS NULL OR da.agent_key IS NULL OR dp.product_key IS NULL OR dd.period_key IS NULL);

SELECT count(*) AS dropped_join_rows
  FROM ow_tp.ops.quarantine_cdw
 WHERE run_id = '__RUN_ID__';

SELECT assert_true(count(*) = 0,
                   'fact_commission: ledger rows dropped by inner joins were quarantined')
  FROM ow_tp.ops.quarantine_cdw
 WHERE run_id = '__RUN_ID__';

MERGE INTO ow_tp.silver.fact_commission_cdw AS f
USING (
    SELECT s.agent_key, s.product_key, s.period_key, s.policy_id, s.split_pct, s.base_premium, s.commission_amt,
           CASE WHEN s.existing_fact_id IS NULL
                THEN m.max_id + row_number() OVER (
                         PARTITION BY (s.existing_fact_id IS NULL)
                         ORDER BY s.policy_id, s.agent_key, s.period_key)
           END AS new_fact_id
      FROM (
        SELECT da.agent_key, dp.product_key, dd.period_key, cl.policy_id, cl.split_pct,
               cl.base_premium, cl.commission_amt, e.fact_id AS existing_fact_id
          FROM ow_tp.bronze.commission_ledger_cdw cl
          JOIN ow_tp.bronze.policies_cdw po ON po.policy_id = cl.policy_id
          JOIN ow_tp.silver.dim_agent_cdw da ON da.agent_id = cl.agent_id
          JOIN ow_tp.silver.dim_product_cdw dp ON dp.product_code = po.product_code
          JOIN ow_tp.silver.dim_period_cdw dd ON dd.period_month = cl.period_month
          LEFT JOIN ow_tp.silver.fact_commission_cdw e
                 ON e.policy_id = cl.policy_id
                AND e.agent_key = da.agent_key
                AND e.period_key = dd.period_key
         WHERE __PERIOD_MONTH__ IS NULL OR cl.period_month = __PERIOD_MONTH__
      ) s
     CROSS JOIN (SELECT coalesce(max(fact_id), 0) AS max_id
                   FROM ow_tp.silver.fact_commission_cdw) m
) AS s
ON f.policy_id = s.policy_id AND f.agent_key = s.agent_key AND f.period_key = s.period_key
WHEN MATCHED THEN UPDATE SET
    f.split_pct = s.split_pct,
    f.base_premium = s.base_premium,
    f.commission_amt = s.commission_amt,
    f.loaded_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT
    (fact_id, agent_key, product_key, period_key, policy_id, split_pct, base_premium, commission_amt, loaded_at)
VALUES
    (s.new_fact_id, s.agent_key, s.product_key, s.period_key, s.policy_id, s.split_pct, s.base_premium,
     s.commission_amt, current_timestamp());
