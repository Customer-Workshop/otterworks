-- Azure-side purge audit. Row inserted as INTENDED before the Db2 unit of work that deletes the key,
-- set to PURGED after that unit of work commits, ROLLED_BACK if it does not. Db2 keeps MIGAUDIT.PURGE_AUDIT.

IF OBJECT_ID(N'mig.purge_audit', N'U') IS NULL
CREATE TABLE mig.purge_audit (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    source_key      NVARCHAR(64)    NOT NULL,
    batch_no        INT             NOT NULL,
    status          NVARCHAR(16)    NOT NULL,
    intended_at     DATETIME2(7)    NOT NULL,
    purged_at       DATETIME2(7)    NULL,
    CONSTRAINT PK_purge_audit PRIMARY KEY (run_id, namespace, table_name, source_key),
    CONSTRAINT FK_purge_audit_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_purge_audit_status CHECK (status IN (N'INTENDED', N'PURGED', N'ROLLED_BACK'))
);
GO
