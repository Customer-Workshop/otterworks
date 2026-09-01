-- Full rebuild corresponding to REFRESH COMPLETE.
CREATE OR REPLACE TABLE ow_tp.gold.mv_agent_commission_summary_cdw
COMMENT 'Commission earned per agent per period (COMMISSION_DW.MV_AGENT_COMMISSION_SUMMARY) - rebuilt in full by each load_commission_facts run'
AS SELECT da.agent_code, da.full_name, dd.period_month, dp.line_of_business,
          CAST(count(*) AS BIGINT) AS policy_rows,
          CAST(sum(f.commission_amt) AS DECIMAL(38,2)) AS total_commission,
          current_timestamp() AS loaded_at
     FROM ow_tp.silver.fact_commission_cdw f
     JOIN ow_tp.silver.dim_agent_cdw da ON da.agent_key = f.agent_key
     JOIN ow_tp.silver.dim_product_cdw dp ON dp.product_key = f.product_key
     JOIN ow_tp.silver.dim_period_cdw dd ON dd.period_key = f.period_key
    GROUP BY da.agent_code, da.full_name, dd.period_month, dp.line_of_business;

SELECT assert_true(
         (SELECT coalesce(sum(policy_rows), 0) FROM ow_tp.gold.mv_agent_commission_summary_cdw)
         = (SELECT count(*) FROM ow_tp.silver.fact_commission_cdw),
         'summary lost fact rows to a dimension join');
