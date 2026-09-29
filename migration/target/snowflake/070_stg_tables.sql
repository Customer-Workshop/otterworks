-- Staging tables: one per migrated table, typed per migration/job/typemaps/db2-to-snowflake.yaml.
-- Db2 TIMESTAMP(12) = TIMESTAMP_NTZ(6) + <col>_NANOS_TAIL holding fraction digits 7-12 (six digits).
-- Snowflake CHAR(n) is VARCHAR(n): fixed-width values keep the padding they were loaded with; the hash
-- expression re-pads keys (RPAD) so target_hash equals the source-side business hash byte for byte.
-- Rows arrive via COPY INTO from Parquet (MATCH_BY_COLUMN_NAME), so column names match the Parquet fields.
-- (namespace, source_key) is not enforced by Snowflake; the driver rejects cross-run duplicates after each COPY.
CREATE TABLE IF NOT EXISTS STG.RETNPLCY (
    RUN_ID                    VARCHAR(64)         NOT NULL,
    NAMESPACE                 VARCHAR(32)         NOT NULL,
    SOURCE_KEY                VARCHAR(64)         NOT NULL,
    RANGE_SEQ                 INTEGER             NOT NULL,
    BATCH_ID                  BIGINT              NOT NULL,
    RAW_BYTES                 BINARY              NOT NULL,
    LOADED_AT                 TIMESTAMP_NTZ(6)    NOT NULL,
    POLICY_CODE               CHAR(4)             NOT NULL,
    POLICY_DESC               VARCHAR(60)         NOT NULL,
    RETENTION_YEARS           SMALLINT            NOT NULL,
    SUCCESSOR_CODE            CHAR(4)             NOT NULL,
    ACTIVE_FLAG               CHAR(1)             NOT NULL,
    DISPOSITION_ACTION        CHAR(4)             NOT NULL,
    EFFECTIVE_TS              TIMESTAMP_NTZ(6)    NOT NULL,
    EFFECTIVE_TS_NANOS_TAIL   INTEGER             NOT NULL,
    CONSTRAINT PK_STG_RETNPLCY PRIMARY KEY (RUN_ID, NAMESPACE, SOURCE_KEY)
);

CREATE TABLE IF NOT EXISTS STG.DOCARCH (
    RUN_ID                      VARCHAR(64)         NOT NULL,
    NAMESPACE                   VARCHAR(32)         NOT NULL,
    SOURCE_KEY                  VARCHAR(64)         NOT NULL,
    RANGE_SEQ                   INTEGER             NOT NULL,
    BATCH_ID                    BIGINT              NOT NULL,
    RAW_BYTES                   BINARY              NOT NULL,
    LOADED_AT                   TIMESTAMP_NTZ(6)    NOT NULL,
    ARCH_KEY                    VARCHAR(16)         NOT NULL,
    DOC_ID                      CHAR(36)            NOT NULL,
    VERSION_NO                  SMALLINT            NOT NULL,
    RETENTION_CLASS             CHAR(4)             NOT NULL,
    LAST_ACCESS_TS              TIMESTAMP_NTZ(6)    NOT NULL,
    LAST_ACCESS_TS_NANOS_TAIL   INTEGER             NOT NULL,
    STORAGE_CHARGE              NUMBER(31, 8)       NOT NULL,
    UNIT_RATE                   NUMBER(18, 8)       NOT NULL,
    OWNER_NAME                  VARCHAR(40)         NOT NULL,
    DISPOSITION_DT              DATE                NOT NULL,
    LEGAL_HOLD_FLAG             CHAR(1)             NOT NULL,
    CHECKSUM_ALG                CHAR(8)             NOT NULL,
    CONTENT_SHA256              CHAR(64)            NOT NULL,
    BYTE_SIZE                   BIGINT              NOT NULL,
    SOURCE_SYS                  CHAR(3)             NOT NULL,
    CONSTRAINT PK_STG_DOCARCH PRIMARY KEY (RUN_ID, NAMESPACE, SOURCE_KEY)
);

CREATE TABLE IF NOT EXISTS STG.FILEAUD (
    RUN_ID                    VARCHAR(64)         NOT NULL,
    NAMESPACE                 VARCHAR(32)         NOT NULL,
    SOURCE_KEY                VARCHAR(64)         NOT NULL,
    RANGE_SEQ                 INTEGER             NOT NULL,
    BATCH_ID                  BIGINT              NOT NULL,
    RAW_BYTES                 BINARY              NOT NULL,
    LOADED_AT                 TIMESTAMP_NTZ(6)    NOT NULL,
    AUDIT_KEY                 CHAR(20)            NOT NULL,
    ARCH_KEY                  VARCHAR(16)         NOT NULL,
    EVENT_TYPE                CHAR(4)             NOT NULL,
    EVENT_TS                  TIMESTAMP_NTZ(6)    NOT NULL,
    EVENT_TS_NANOS_TAIL       INTEGER             NOT NULL,
    ACTOR_ID                  CHAR(12)            NOT NULL,
    RETENTION_CLASS           CHAR(4)             NOT NULL,
    DISPOSITION_CODE          CHAR(2)             NOT NULL,
    CLIENT_IP                 VARCHAR(15)         NOT NULL,
    DETAIL_TEXT               VARCHAR(40)         NOT NULL,
    CONSTRAINT PK_STG_FILEAUD PRIMARY KEY (RUN_ID, NAMESPACE, SOURCE_KEY)
);
