-- Deliberately dead scanner target: no live job writes or reads this table.
CREATE TABLE IF NOT EXISTS core.stg_orders_dedup_audit (
    audit_id       BIGINT       NOT NULL ENCODE az64,
    run_ts         TIMESTAMP    ENCODE az64,
    source_rows    BIGINT       ENCODE az64,
    retained_rows  BIGINT       ENCODE az64,
    duplicate_rows BIGINT       ENCODE az64,
    PRIMARY KEY (audit_id)
)
DISTSTYLE ALL
SORTKEY (run_ts);
