-- run_ledger: one row per (run_id, namespace, table_name); each stage writes ONLY its own columns.
-- stage_log: one row per stage attempt (and per table within the stage) for timing evidence.

IF OBJECT_ID(N'mig.run_ledger', N'U') IS NULL
CREATE TABLE mig.run_ledger (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    table_order     INT             NOT NULL,
    table_role      NVARCHAR(16)    NOT NULL,
    extracted       BIGINT          NULL,   -- EXTRACT: rows written to fixed-width files
    extract_files   INT             NULL,   -- EXTRACT: files (= key ranges) written
    loaded          BIGINT          NULL,   -- LOAD: rows inserted into stg
    rejected        BIGINT          NULL,   -- LOAD: rows written to mig.rejects with stage LOAD
    validated       BIGINT          NULL,   -- VALIDATE: rows with status VALIDATED (purge-safe for data tables)
    validate_failed BIGINT          NULL,   -- VALIDATE: rows with status FAILED
    purge_intended  BIGINT          NULL,   -- PURGE: purge-safe keys selected for deletion
    purged          BIGINT          NULL,   -- PURGE: keys deleted and committed in Db2 (0 on dry run)
    purge_dry_run   BIT             NULL,
    updated_at      DATETIME2(3)    NOT NULL CONSTRAINT DF_run_ledger_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_run_ledger PRIMARY KEY (run_id, namespace, table_name),
    CONSTRAINT FK_run_ledger_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_run_ledger_role CHECK (table_role IN (N'data', N'reference'))
);
GO
IF OBJECT_ID(N'mig.stage_log', N'U') IS NULL
CREATE TABLE mig.stage_log (
    stage_log_id    BIGINT IDENTITY(1, 1) NOT NULL,
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    stage           NVARCHAR(16)    NOT NULL,
    table_name      NVARCHAR(128)   NULL,   -- NULL = the stage as a whole
    host            NVARCHAR(8)     NOT NULL,
    attempt         INT             NOT NULL,
    status          NVARCHAR(16)    NOT NULL,
    rows_processed  BIGINT          NULL,
    started_at      DATETIME2(3)    NOT NULL,
    finished_at     DATETIME2(3)    NULL,
    message         NVARCHAR(4000)  NULL,
    CONSTRAINT PK_stage_log PRIMARY KEY (stage_log_id),
    CONSTRAINT CK_stage_log_stage CHECK (stage IN (N'INIT', N'EXTRACT', N'LOAD', N'VALIDATE', N'PURGE', N'RECONCILE')),
    CONSTRAINT CK_stage_log_host CHECK (host IN (N'eks', N'aca', N'local')),
    CONSTRAINT CK_stage_log_status CHECK (status IN (N'RUNNING', N'OK', N'FAILED'))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_stage_log_run' AND object_id = OBJECT_ID(N'mig.stage_log'))
CREATE INDEX IX_stage_log_run ON mig.stage_log (run_id, namespace, stage);
GO
