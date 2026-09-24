-- Restart unit for EXTRACT and LOAD. Ranges are inclusive [key_from, key_to] in Db2 ORDER BY key order.

IF OBJECT_ID(N'mig.key_ranges', N'U') IS NULL
CREATE TABLE mig.key_ranges (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    range_seq       INT             NOT NULL,
    key_from        NVARCHAR(64)    NOT NULL,
    key_to          NVARCHAR(64)    NOT NULL,
    rows_extracted  BIGINT          NULL,
    file_name       NVARCHAR(260)   NULL,
    file_sha256     CHAR(64)        NULL,
    file_bytes      BIGINT          NULL,
    extract_status  NVARCHAR(16)    NOT NULL,
    load_status     NVARCHAR(16)    NOT NULL,
    extracted_at    DATETIME2(3)    NULL,
    loaded_at       DATETIME2(3)    NULL,
    CONSTRAINT PK_key_ranges PRIMARY KEY (run_id, namespace, table_name, range_seq),
    CONSTRAINT FK_key_ranges_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_key_ranges_extract CHECK (extract_status IN (N'PLANNED', N'RUNNING', N'DONE', N'FAILED')),
    CONSTRAINT CK_key_ranges_load CHECK (load_status IN (N'PENDING', N'RUNNING', N'DONE', N'FAILED'))
);
GO
