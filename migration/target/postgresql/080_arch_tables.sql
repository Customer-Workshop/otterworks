-- Archive tables: the system of record after promotion (§6.4). Read by report-service and audit-service.
CREATE TABLE IF NOT EXISTS arch."RETNPLCY" (
    "POLICY_CODE"             CHAR(4)         NOT NULL,
    "POLICY_DESC"             VARCHAR(60)     NOT NULL,
    "RETENTION_YEARS"         SMALLINT        NOT NULL,
    "SUCCESSOR_CODE"          CHAR(4)         NOT NULL,
    "ACTIVE_FLAG"             CHAR(1)         NOT NULL,
    "DISPOSITION_ACTION"      CHAR(4)         NOT NULL,
    "EFFECTIVE_TS"            TIMESTAMP(6)    NOT NULL,
    "EFFECTIVE_TS_NANOS_TAIL" INTEGER         NOT NULL,
    source_key                VARCHAR(64) COLLATE "C"     NOT NULL,
    row_hash                  BYTEA           NOT NULL,
    namespace                 VARCHAR(32)     NOT NULL,
    migrated_run_id           VARCHAR(64)     NOT NULL,
    migrated_at               TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT pk_arch_retnplcy PRIMARY KEY ("POLICY_CODE"),
    CONSTRAINT ck_arch_retnplcy_tail CHECK ("EFFECTIVE_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);

CREATE TABLE IF NOT EXISTS arch."DOCARCH" (
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
    source_key                  VARCHAR(64) COLLATE "C"     NOT NULL,
    row_hash                    BYTEA           NOT NULL,
    namespace                   VARCHAR(32)     NOT NULL,
    migrated_run_id             VARCHAR(64)     NOT NULL,
    migrated_at                 TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT pk_arch_docarch PRIMARY KEY ("ARCH_KEY"),
    CONSTRAINT fk_arch_docarch_retnplcy FOREIGN KEY ("RETENTION_CLASS") REFERENCES arch."RETNPLCY" ("POLICY_CODE"),
    CONSTRAINT ck_arch_docarch_tail CHECK ("LAST_ACCESS_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);
CREATE INDEX IF NOT EXISTS ix_arch_docarch_doc ON arch."DOCARCH" ("DOC_ID", "VERSION_NO");

CREATE TABLE IF NOT EXISTS arch."FILEAUD" (
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
    source_key                VARCHAR(64) COLLATE "C"     NOT NULL,
    row_hash                  BYTEA           NOT NULL,
    namespace                 VARCHAR(32)     NOT NULL,
    migrated_run_id           VARCHAR(64)     NOT NULL,
    migrated_at               TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT pk_arch_fileaud PRIMARY KEY ("AUDIT_KEY"),
    CONSTRAINT fk_arch_fileaud_docarch FOREIGN KEY ("ARCH_KEY") REFERENCES arch."DOCARCH" ("ARCH_KEY"),
    CONSTRAINT ck_arch_fileaud_tail CHECK ("EVENT_TS_NANOS_TAIL" BETWEEN 0 AND 999999)
);
CREATE INDEX IF NOT EXISTS ix_arch_fileaud_parent ON arch."FILEAUD" ("ARCH_KEY", "EVENT_TS");
