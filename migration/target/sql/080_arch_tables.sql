-- Final migrated tables: the converted columns of stg.<T> plus provenance. Rows are promoted from stg by
-- VALIDATE only when status = VALIDATED. This is what ARCHIVE_STORE=azuresql reads (CONTRACTS.md §10.4).

IF OBJECT_ID(N'arch.RETNPLCY', N'U') IS NULL
CREATE TABLE arch.RETNPLCY (
    POLICY_CODE             NCHAR(4)        NOT NULL,
    POLICY_DESC             NVARCHAR(60)    NOT NULL,
    RETENTION_YEARS         SMALLINT        NOT NULL,
    SUCCESSOR_CODE          NCHAR(4)        NOT NULL,
    ACTIVE_FLAG             NCHAR(1)        NOT NULL,
    DISPOSITION_ACTION      NCHAR(4)        NOT NULL,
    EFFECTIVE_TS            DATETIME2(7)    NOT NULL,
    EFFECTIVE_TS_NANOS_TAIL INT             NOT NULL,
    source_key              NVARCHAR(64)    NOT NULL,
    row_hash                BINARY(32)      NOT NULL,
    namespace               NVARCHAR(32)    NOT NULL,
    migrated_run_id         NVARCHAR(64)    NOT NULL,
    migrated_at             DATETIME2(3)    NOT NULL CONSTRAINT DF_arch_RETNPLCY_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_arch_RETNPLCY PRIMARY KEY (POLICY_CODE),
    CONSTRAINT CK_arch_RETNPLCY_tail CHECK (EFFECTIVE_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO

IF OBJECT_ID(N'arch.DOCARCH', N'U') IS NULL
CREATE TABLE arch.DOCARCH (
    ARCH_KEY                  NVARCHAR(16)    NOT NULL,
    DOC_ID                    NCHAR(36)       NOT NULL,
    VERSION_NO                SMALLINT        NOT NULL,
    RETENTION_CLASS           NCHAR(4)        NOT NULL,
    LAST_ACCESS_TS            DATETIME2(7)    NOT NULL,
    LAST_ACCESS_TS_NANOS_TAIL INT             NOT NULL,
    STORAGE_CHARGE            DECIMAL(31, 8)  NOT NULL,
    UNIT_RATE                 DECIMAL(18, 8)  NOT NULL,
    OWNER_NAME                NVARCHAR(40)    NOT NULL,
    DISPOSITION_DT            DATE            NOT NULL,
    LEGAL_HOLD_FLAG           NCHAR(1)        NOT NULL,
    CHECKSUM_ALG              NCHAR(8)        NOT NULL,
    CONTENT_SHA256            NCHAR(64)       NOT NULL,
    BYTE_SIZE                 BIGINT          NOT NULL,
    SOURCE_SYS                NCHAR(3)        NOT NULL,
    source_key                NVARCHAR(64)    NOT NULL,
    row_hash                  BINARY(32)      NOT NULL,
    namespace                 NVARCHAR(32)    NOT NULL,
    migrated_run_id           NVARCHAR(64)    NOT NULL,
    migrated_at               DATETIME2(3)    NOT NULL CONSTRAINT DF_arch_DOCARCH_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_arch_DOCARCH PRIMARY KEY (ARCH_KEY),
    CONSTRAINT FK_arch_DOCARCH_RETNPLCY FOREIGN KEY (RETENTION_CLASS) REFERENCES arch.RETNPLCY (POLICY_CODE),
    CONSTRAINT CK_arch_DOCARCH_tail CHECK (LAST_ACCESS_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_arch_DOCARCH_doc' AND object_id = OBJECT_ID(N'arch.DOCARCH'))
CREATE INDEX IX_arch_DOCARCH_doc ON arch.DOCARCH (DOC_ID, VERSION_NO);
GO

IF OBJECT_ID(N'arch.FILEAUD', N'U') IS NULL
CREATE TABLE arch.FILEAUD (
    AUDIT_KEY               NCHAR(20)       NOT NULL,
    ARCH_KEY                NVARCHAR(16)    NOT NULL,
    EVENT_TYPE              NCHAR(4)        NOT NULL,
    EVENT_TS                DATETIME2(7)    NOT NULL,
    EVENT_TS_NANOS_TAIL     INT             NOT NULL,
    ACTOR_ID                NCHAR(12)       NOT NULL,
    RETENTION_CLASS         NCHAR(4)        NOT NULL,
    DISPOSITION_CODE        NCHAR(2)        NOT NULL,
    CLIENT_IP               NVARCHAR(15)    NOT NULL,
    DETAIL_TEXT             NVARCHAR(40)    NOT NULL,
    source_key              NVARCHAR(64)    NOT NULL,
    row_hash                BINARY(32)      NOT NULL,
    namespace               NVARCHAR(32)    NOT NULL,
    migrated_run_id         NVARCHAR(64)    NOT NULL,
    migrated_at             DATETIME2(3)    NOT NULL CONSTRAINT DF_arch_FILEAUD_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_arch_FILEAUD PRIMARY KEY (AUDIT_KEY),
    CONSTRAINT FK_arch_FILEAUD_DOCARCH FOREIGN KEY (ARCH_KEY) REFERENCES arch.DOCARCH (ARCH_KEY),
    CONSTRAINT CK_arch_FILEAUD_tail CHECK (EVENT_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_arch_FILEAUD_parent' AND object_id = OBJECT_ID(N'arch.FILEAUD'))
CREATE INDEX IX_arch_FILEAUD_parent ON arch.FILEAUD (ARCH_KEY, EVENT_TS);
GO
