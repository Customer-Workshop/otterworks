-- fact_commission: COMMISSION_DW.FACT_COMMISSION -> ow_tp.silver.fact_commission_cdw
-- fact_id values are carried over verbatim from the legacy warehouse baseline
-- (DEC-003); new rows are allocated by the loader over unmatched source rows.
DROP TABLE IF EXISTS ow_tp.silver.fact_commission_cdw;

CREATE TABLE ow_tp.silver.fact_commission_cdw (
    fact_id        BIGINT        NOT NULL,
    agent_key      BIGINT        NOT NULL,
    product_key    BIGINT        NOT NULL,
    period_key     BIGINT        NOT NULL,
    policy_id      BIGINT        NOT NULL,
    split_pct      DECIMAL(5,2)  NOT NULL,
    base_premium   DECIMAL(12,2) NOT NULL,
    commission_amt DECIMAL(12,2) NOT NULL,
    loaded_at      TIMESTAMP     NOT NULL
) USING DELTA CLUSTER BY (period_key, agent_key)
COMMENT 'Commission fact (COMMISSION_DW.FACT_COMMISSION) - fact_id preserved from the legacy warehouse, MERGE key (policy_id, agent_key, period_key) = UX_FACT_ROW';

CREATE TABLE IF NOT EXISTS ow_tp.ops.run_log_cdw (
    run_id STRING NOT NULL, unit STRING NOT NULL, period_month STRING,
    rows_merged BIGINT, rows_updated BIGINT, rows_inserted BIGINT, dropped_join_rows BIGINT NOT NULL,
    status STRING NOT NULL, detail STRING, started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP NOT NULL
) USING DELTA COMMENT 'One row per load_commission_facts run';

CREATE TABLE IF NOT EXISTS ow_tp.ops.quarantine_cdw (
    run_id STRING NOT NULL, unit STRING NOT NULL, ledger_id BIGINT, policy_id BIGINT, agent_id BIGINT,
    period_month STRING, reason STRING NOT NULL, quarantined_at TIMESTAMP NOT NULL
) USING DELTA COMMENT 'Ledger rows the fact load could not join to a policy or dimension';
