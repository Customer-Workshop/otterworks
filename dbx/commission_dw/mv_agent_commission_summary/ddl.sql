-- mv_agent_commission_summary: COMMISSION_DW.MV_AGENT_COMMISSION_SUMMARY
-- -> ow_tp.gold.mv_agent_commission_summary_cdw
CREATE TABLE IF NOT EXISTS ow_tp.gold.mv_agent_commission_summary_cdw (
    agent_code STRING NOT NULL,
    full_name STRING NOT NULL,
    period_month STRING NOT NULL,
    line_of_business STRING NOT NULL,
    policy_rows BIGINT NOT NULL,
    total_commission DECIMAL(38,2) NOT NULL,
    loaded_at TIMESTAMP NOT NULL
) USING DELTA
COMMENT 'Commission earned per agent per period (COMMISSION_DW.MV_AGENT_COMMISSION_SUMMARY)';
