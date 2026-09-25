-- Every failed source row, LOAD or VALIDATE. At most one row per key per run (highest-priority rule wins).

IF OBJECT_ID(N'mig.rejects', N'U') IS NULL
CREATE TABLE mig.rejects (
    reject_id       BIGINT IDENTITY(1, 1) NOT NULL,
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    source_key      NVARCHAR(64)    NOT NULL,   -- canonical key text, trailing spaces preserved
    stage           NVARCHAR(16)    NOT NULL,
    rule_name       NVARCHAR(64)    NOT NULL,
    field           NVARCHAR(128)   NULL,
    sqlstate        CHAR(5)         NULL,
    native_error    INT             NULL,
    error           NVARCHAR(4000)  NOT NULL,
    raw_bytes       VARBINARY(MAX)  NULL,       -- LOAD: the full fixed-width record
    field_bytes     VARBINARY(8000) NULL,       -- LOAD: raw bytes of the failing field
    range_seq       INT             NULL,
    batch_id        INT             NULL,
    created_at      DATETIME2(3)    NOT NULL CONSTRAINT DF_rejects_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_rejects PRIMARY KEY (reject_id),
    CONSTRAINT UQ_rejects_key UNIQUE (run_id, namespace, table_name, source_key),
    CONSTRAINT FK_rejects_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_rejects_stage CHECK (stage IN (N'LOAD', N'VALIDATE'))
);
GO
