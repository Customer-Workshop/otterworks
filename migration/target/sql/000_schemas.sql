-- Azure SQL Database (compatibility level 160). Idempotent. Batches separated by lines containing only GO;
-- 'ldm init' splits on ^GO$ and applies files in name order, recording each in mig.schema_version.

IF SCHEMA_ID(N'mig') IS NULL EXEC (N'CREATE SCHEMA mig');
GO
IF SCHEMA_ID(N'stg') IS NULL EXEC (N'CREATE SCHEMA stg');
GO
IF SCHEMA_ID(N'arch') IS NULL EXEC (N'CREATE SCHEMA arch');
GO
IF OBJECT_ID(N'mig.schema_version', N'U') IS NULL
CREATE TABLE mig.schema_version (
    file_name       NVARCHAR(128)   NOT NULL,
    file_sha256     CHAR(64)        NOT NULL,
    applied_at      DATETIME2(3)    NOT NULL CONSTRAINT DF_schema_version_applied DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_schema_version PRIMARY KEY (file_name)
);
GO
