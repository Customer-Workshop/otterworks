-- One row per (run_id, namespace). Written by every stage; closes/exit_code set by RECONCILE.

IF OBJECT_ID(N'mig.runs', N'U') IS NULL
CREATE TABLE mig.runs (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    status          NVARCHAR(16)    NOT NULL,
    purge_enabled   BIT             NOT NULL,
    manifest_sha256 CHAR(64)        NULL,
    job_image       NVARCHAR(256)   NULL,
    started_at      DATETIME2(3)    NOT NULL CONSTRAINT DF_runs_started DEFAULT SYSUTCDATETIME(),
    finished_at     DATETIME2(3)    NULL,
    exit_code       INT             NULL,
    closes          BIT             NULL,
    CONSTRAINT PK_runs PRIMARY KEY (run_id, namespace),
    CONSTRAINT CK_runs_status CHECK (status IN (N'RUNNING', N'CLOSED', N'FAILED', N'ABANDONED'))
);
GO
IF OBJECT_ID(N'mig.run_sessions', N'U') IS NULL
CREATE TABLE mig.run_sessions (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    ordinal         INT             NOT NULL,
    label           NVARCHAR(128)   NOT NULL,
    url             NVARCHAR(512)   NOT NULL,
    CONSTRAINT PK_run_sessions PRIMARY KEY (run_id, namespace, ordinal),
    CONSTRAINT FK_run_sessions_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace)
);
GO
