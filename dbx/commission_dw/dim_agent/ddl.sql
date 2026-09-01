-- dim_agent: COMMISSION_DW.DIM_AGENT -> ow_tp.silver.dim_agent_cdw
-- Source DDL: services/industry-solutions/insurance/db/olap/01_star_schema.sql (dim_agent)
-- agent_key is a NUMBER identity in the legacy warehouse; here it is a plain BIGINT
-- whose values are carried over verbatim from the DIM_AGENT baseline snapshot (DEC-003)
-- and allocated as max(agent_key) + row_number() for new agents by the loader.
-- Run start: drop and recreate so a relaunch never reconciles against its own debris.
DROP TABLE IF EXISTS ow_tp.silver.dim_agent_cdw;

CREATE TABLE ow_tp.silver.dim_agent_cdw (
    agent_key  BIGINT    NOT NULL,
    agent_id   BIGINT    NOT NULL,
    agent_code STRING    NOT NULL,
    full_name  STRING    NOT NULL,
    status     STRING    NOT NULL,
    loaded_at  TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Agent dimension (COMMISSION_DW.DIM_AGENT) - surrogate agent_key preserved from the legacy warehouse';
