-- Snowflake archive store (SNOWFLAKE-PORT-SPEC.md §3, CONTRACTS.md §8). One database per tenant
-- (OTTERWORKS_LDM_<TOKEN>, created by the deploy script as LDM_ADMIN); `ldm init` runs these files inside it in
-- file-name order, tracked in MIG.SCHEMA_VERSION. The transactional control plane (runs, ledger, key ranges,
-- rejects, purge audit) stays in the tenant's PostgreSQL database; MIG.* here is a read-only mirror of the
-- verdicts so promotion and the reporting views are set-based inside Snowflake. Every statement is idempotent.
CREATE SCHEMA IF NOT EXISTS MIG;
CREATE SCHEMA IF NOT EXISTS STG;
CREATE SCHEMA IF NOT EXISTS ARCH;

CREATE TABLE IF NOT EXISTS MIG.SCHEMA_VERSION (
    FILE_NAME       VARCHAR(128)        NOT NULL,
    FILE_SHA256     VARCHAR(64)         NOT NULL,
    APPLIED_AT      TIMESTAMP_NTZ(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ(3),
    CONSTRAINT PK_SCHEMA_VERSION PRIMARY KEY (FILE_NAME)
);

-- Internal stage the job PUTs one Parquet file per load batch into; COPY INTO ... PURGE = TRUE removes it again.
CREATE STAGE IF NOT EXISTS STG.LDM_STAGE
    FILE_FORMAT = (TYPE = PARQUET USE_LOGICAL_TYPE = TRUE BINARY_AS_TEXT = FALSE)
    COMMENT = 'ldm load batches (Parquet); files are purged by COPY INTO';
