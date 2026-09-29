-- Staging tables: one per migrated table, typed per migration/job/typemaps/db2-to-postgresql.yaml.
-- Db2 TIMESTAMP(12) = TIMESTAMP(6) + <col>_NANOS_TAIL holding fraction digits 7-12 (six digits).
-- Identifiers keep the Db2 upper-case spelling and are therefore quoted (the driver quotes them too).
CREATE TABLE IF NOT EXISTS stg."RETNPLCY" (
    run_id                    VARCHAR(64)     NOT NULL,
    namespace                 VARCHAR(32)     NOT NULL,
    source_key                VARCHAR(64) COLLATE "C"     NOT NULL,
    range_seq                 INTEGER         NOT NULL,
    batch_id                  INTEGER         NOT NULL,
    raw_bytes                 BYTEA           NOT NULL,
    row_hash                  BYTEA           NULL,
    loaded_at                 TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    "POLICY_CODE"             CHAR(4)         NOT NULL,
    "POLICY_DESC"             VARCHAR(60)     NOT NULL,
    "RETENTION_YEARS"         SMALLINT        NOT NULL,
    "SUCCESSOR_CODE"          CHAR(4)         NOT NULL,
    "ACTIVE_FLAG"             CHAR(1)         NOT NULL,
    "DISPOSITION_ACTION"      CHAR(4)         NOT NULL,
    "EFFECTIVE_TS"            TIMESTAMP(6)    NOT NULL,
    "EFFECTIVE_TS_NANOS_TAIL" INTEGER         NOT NULL,
    CONSTRAINT pk_stg_retnplcy PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT ck_stg_retnplcy_tail CHECK ("EFFECTIVE_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_stg_retnplcy_source_key ON stg."RETNPLCY" (namespace, source_key);

CREATE TABLE IF NOT EXISTS stg."DOCARCH" (
    run_id                      VARCHAR(64)     NOT NULL,
    namespace                   VARCHAR(32)     NOT NULL,
    source_key                  VARCHAR(64) COLLATE "C"     NOT NULL,
    range_seq                   INTEGER         NOT NULL,
    batch_id                    INTEGER         NOT NULL,
    raw_bytes                   BYTEA           NOT NULL,
    row_hash                    BYTEA           NULL,
    loaded_at                   TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    "ARCH_KEY"                  VARCHAR(16)     NOT NULL,
    "DOC_ID"                    CHAR(36)        NOT NULL,
    "VERSION_NO"                SMALLINT        NOT NULL,
    "RETENTION_CLASS"           CHAR(4)         NOT NULL,
    "LAST_ACCESS_TS"            TIMESTAMP(6)    NOT NULL,
    "LAST_ACCESS_TS_NANOS_TAIL" INTEGER         NOT NULL,
    "STORAGE_CHARGE"            NUMERIC(31, 8)  NOT NULL,
    "UNIT_RATE"                 NUMERIC(18, 8)  NOT NULL,
    "OWNER_NAME"                VARCHAR(40)     NOT NULL,
    "DISPOSITION_DT"            DATE            NOT NULL,
    "LEGAL_HOLD_FLAG"           CHAR(1)         NOT NULL,
    "CHECKSUM_ALG"              CHAR(8)         NOT NULL,
    "CONTENT_SHA256"            CHAR(64)        NOT NULL,
    "BYTE_SIZE"                 BIGINT          NOT NULL,
    "SOURCE_SYS"                CHAR(3)         NOT NULL,
    CONSTRAINT pk_stg_docarch PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT ck_stg_docarch_tail CHECK ("LAST_ACCESS_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_stg_docarch_source_key ON stg."DOCARCH" (namespace, source_key);
CREATE INDEX IF NOT EXISTS ix_stg_docarch_class ON stg."DOCARCH" (run_id, namespace, "RETENTION_CLASS") INCLUDE ("STORAGE_CHARGE");

CREATE TABLE IF NOT EXISTS stg."FILEAUD" (
    run_id                    VARCHAR(64)     NOT NULL,
    namespace                 VARCHAR(32)     NOT NULL,
    source_key                VARCHAR(64) COLLATE "C"     NOT NULL,
    range_seq                 INTEGER         NOT NULL,
    batch_id                  INTEGER         NOT NULL,
    raw_bytes                 BYTEA           NOT NULL,
    row_hash                  BYTEA           NULL,
    loaded_at                 TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    "AUDIT_KEY"               CHAR(20)        NOT NULL,
    "ARCH_KEY"                VARCHAR(16)     NOT NULL,
    "EVENT_TYPE"              CHAR(4)         NOT NULL,
    "EVENT_TS"                TIMESTAMP(6)    NOT NULL,
    "EVENT_TS_NANOS_TAIL"     INTEGER         NOT NULL,
    "ACTOR_ID"                CHAR(12)        NOT NULL,
    "RETENTION_CLASS"         CHAR(4)         NOT NULL,
    "DISPOSITION_CODE"        CHAR(2)         NOT NULL,
    "CLIENT_IP"               VARCHAR(15)     NOT NULL,
    "DETAIL_TEXT"             VARCHAR(40)     NOT NULL,
    CONSTRAINT pk_stg_fileaud PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT ck_stg_fileaud_tail CHECK ("EVENT_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_stg_fileaud_source_key ON stg."FILEAUD" (namespace, source_key);
CREATE INDEX IF NOT EXISTS ix_stg_fileaud_parent ON stg."FILEAUD" (run_id, namespace, "ARCH_KEY");
