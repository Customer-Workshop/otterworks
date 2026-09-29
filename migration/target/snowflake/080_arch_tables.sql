-- Archive tables: the system of record after promotion (§6.4). Read by report-service / audit-service through the
-- Snowflake reader role. Keys/FKs are declarative in Snowflake (not enforced); promotion is the guard.
CREATE TABLE IF NOT EXISTS ARCH.RETNPLCY (
    POLICY_CODE               CHAR(4)             NOT NULL,
    POLICY_DESC               VARCHAR(60)         NOT NULL,
    RETENTION_YEARS           SMALLINT            NOT NULL,
    SUCCESSOR_CODE            CHAR(4)             NOT NULL,
    ACTIVE_FLAG               CHAR(1)             NOT NULL,
    DISPOSITION_ACTION        CHAR(4)             NOT NULL,
    EFFECTIVE_TS              TIMESTAMP_NTZ(6)    NOT NULL,
    EFFECTIVE_TS_NANOS_TAIL   INTEGER             NOT NULL,
    SOURCE_KEY                VARCHAR(64)         NOT NULL,
    ROW_HASH                  BINARY(32)          NOT NULL,
    NAMESPACE                 VARCHAR(32)         NOT NULL,
    MIGRATED_RUN_ID           VARCHAR(64)         NOT NULL,
    MIGRATED_AT               TIMESTAMP_NTZ(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ(3),
    CONSTRAINT PK_ARCH_RETNPLCY PRIMARY KEY (NAMESPACE, POLICY_CODE)
);

CREATE TABLE IF NOT EXISTS ARCH.DOCARCH (
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
    SOURCE_KEY                  VARCHAR(64)         NOT NULL,
    ROW_HASH                    BINARY(32)          NOT NULL,
    NAMESPACE                   VARCHAR(32)         NOT NULL,
    MIGRATED_RUN_ID             VARCHAR(64)         NOT NULL,
    MIGRATED_AT                 TIMESTAMP_NTZ(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ(3),
    CONSTRAINT PK_ARCH_DOCARCH PRIMARY KEY (NAMESPACE, ARCH_KEY),
    CONSTRAINT FK_ARCH_DOCARCH_RETNPLCY FOREIGN KEY (NAMESPACE, RETENTION_CLASS)
        REFERENCES ARCH.RETNPLCY (NAMESPACE, POLICY_CODE)
);

CREATE TABLE IF NOT EXISTS ARCH.FILEAUD (
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
    SOURCE_KEY                VARCHAR(64)         NOT NULL,
    ROW_HASH                  BINARY(32)          NOT NULL,
    NAMESPACE                 VARCHAR(32)         NOT NULL,
    MIGRATED_RUN_ID           VARCHAR(64)         NOT NULL,
    MIGRATED_AT               TIMESTAMP_NTZ(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ(3),
    CONSTRAINT PK_ARCH_FILEAUD PRIMARY KEY (NAMESPACE, AUDIT_KEY),
    CONSTRAINT FK_ARCH_FILEAUD_DOCARCH FOREIGN KEY (NAMESPACE, ARCH_KEY) REFERENCES ARCH.DOCARCH (NAMESPACE, ARCH_KEY)
);
