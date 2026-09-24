-- Staging: one table per source table. Provenance columns first, then converted columns named exactly
-- as the Db2 columns. A row exists here only if EVERY field converted; failures go to mig.rejects.
-- UX_*_source_key spans runs: rows left by a non-CLOSED run block reloading the same key (MIG-06).
-- <COL>_NANOS_TAIL = fraction digits 8..12 of a Db2 TIMESTAMP(12) (0..99999), DATETIME2(7) holds digits 1..7.

IF OBJECT_ID(N'stg.RETNPLCY', N'U') IS NULL
CREATE TABLE stg.RETNPLCY (
    run_id                  NVARCHAR(64)    NOT NULL,
    namespace               NVARCHAR(32)    NOT NULL,
    source_key              NVARCHAR(64)    NOT NULL,
    range_seq               INT             NOT NULL,
    batch_id                INT             NOT NULL,
    raw_bytes               VARBINARY(MAX)  NOT NULL,
    row_hash                BINARY(32)      NULL,
    loaded_at               DATETIME2(3)    NOT NULL CONSTRAINT DF_stg_RETNPLCY_loaded DEFAULT SYSUTCDATETIME(),
    POLICY_CODE             NCHAR(4)        NOT NULL,
    POLICY_DESC             NVARCHAR(60)    NOT NULL,
    RETENTION_YEARS         SMALLINT        NOT NULL,
    SUCCESSOR_CODE          NCHAR(4)        NOT NULL,
    ACTIVE_FLAG             NCHAR(1)        NOT NULL,
    DISPOSITION_ACTION      NCHAR(4)        NOT NULL,
    EFFECTIVE_TS            DATETIME2(7)    NOT NULL,
    EFFECTIVE_TS_NANOS_TAIL INT             NOT NULL,
    CONSTRAINT PK_stg_RETNPLCY PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT CK_stg_RETNPLCY_tail CHECK (EFFECTIVE_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_stg_RETNPLCY_source_key' AND object_id = OBJECT_ID(N'stg.RETNPLCY'))
CREATE UNIQUE INDEX UX_stg_RETNPLCY_source_key ON stg.RETNPLCY (namespace, source_key);
GO

IF OBJECT_ID(N'stg.DOCARCH', N'U') IS NULL
CREATE TABLE stg.DOCARCH (
    run_id                    NVARCHAR(64)    NOT NULL,
    namespace                 NVARCHAR(32)    NOT NULL,
    source_key                NVARCHAR(64)    NOT NULL,
    range_seq                 INT             NOT NULL,
    batch_id                  INT             NOT NULL,
    raw_bytes                 VARBINARY(MAX)  NOT NULL,
    row_hash                  BINARY(32)      NULL,
    loaded_at                 DATETIME2(3)    NOT NULL CONSTRAINT DF_stg_DOCARCH_loaded DEFAULT SYSUTCDATETIME(),
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
    CONSTRAINT PK_stg_DOCARCH PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT CK_stg_DOCARCH_tail CHECK (LAST_ACCESS_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_stg_DOCARCH_source_key' AND object_id = OBJECT_ID(N'stg.DOCARCH'))
CREATE UNIQUE INDEX UX_stg_DOCARCH_source_key ON stg.DOCARCH (namespace, source_key);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_stg_DOCARCH_class' AND object_id = OBJECT_ID(N'stg.DOCARCH'))
CREATE INDEX IX_stg_DOCARCH_class ON stg.DOCARCH (run_id, namespace, RETENTION_CLASS) INCLUDE (STORAGE_CHARGE);
GO

IF OBJECT_ID(N'stg.FILEAUD', N'U') IS NULL
CREATE TABLE stg.FILEAUD (
    run_id                  NVARCHAR(64)    NOT NULL,
    namespace               NVARCHAR(32)    NOT NULL,
    source_key              NVARCHAR(64)    NOT NULL,
    range_seq               INT             NOT NULL,
    batch_id                INT             NOT NULL,
    raw_bytes               VARBINARY(MAX)  NOT NULL,
    row_hash                BINARY(32)      NULL,
    loaded_at               DATETIME2(3)    NOT NULL CONSTRAINT DF_stg_FILEAUD_loaded DEFAULT SYSUTCDATETIME(),
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
    CONSTRAINT PK_stg_FILEAUD PRIMARY KEY (run_id, namespace, source_key),
    CONSTRAINT CK_stg_FILEAUD_tail CHECK (EVENT_TS_NANOS_TAIL BETWEEN 0 AND 99999)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_stg_FILEAUD_source_key' AND object_id = OBJECT_ID(N'stg.FILEAUD'))
CREATE UNIQUE INDEX UX_stg_FILEAUD_source_key ON stg.FILEAUD (namespace, source_key);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_stg_FILEAUD_parent' AND object_id = OBJECT_ID(N'stg.FILEAUD'))
CREATE INDEX IX_stg_FILEAUD_parent ON stg.FILEAUD (run_id, namespace, ARCH_KEY);
GO
