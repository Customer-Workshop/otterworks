-- validation: per-key outcome of VALIDATE; purge_safe = 1 only for fully validated rows of data tables.
-- class_totals: per-class aggregates computed on each side, kept as report evidence (MIG-07).

IF OBJECT_ID(N'mig.validation', N'U') IS NULL
CREATE TABLE mig.validation (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    source_key      NVARCHAR(64)    NOT NULL,
    source_hash     BINARY(32)      NOT NULL,
    target_hash     BINARY(32)      NULL,
    status          NVARCHAR(16)    NOT NULL,
    rule_name       NVARCHAR(64)    NULL,
    purge_safe      BIT             NOT NULL,
    validated_at    DATETIME2(3)    NOT NULL CONSTRAINT DF_validation_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_validation PRIMARY KEY (run_id, namespace, table_name, source_key),
    CONSTRAINT FK_validation_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_validation_status CHECK (status IN (N'VALIDATED', N'FAILED')),
    CONSTRAINT CK_validation_safe CHECK (purge_safe = 0 OR status = N'VALIDATED')
);
GO
IF OBJECT_ID(N'mig.class_totals', N'U') IS NULL
CREATE TABLE mig.class_totals (
    run_id          NVARCHAR(64)    NOT NULL,
    namespace       NVARCHAR(32)    NOT NULL,
    table_name      NVARCHAR(128)   NOT NULL,
    class_code      NVARCHAR(8)     NOT NULL,
    side            NVARCHAR(6)     NOT NULL,
    row_count       BIGINT          NOT NULL,
    charge_sum      DECIMAL(38, 8)  NULL,
    CONSTRAINT PK_class_totals PRIMARY KEY (run_id, namespace, table_name, class_code, side),
    CONSTRAINT FK_class_totals_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT CK_class_totals_side CHECK (side IN (N'SOURCE', N'TARGET'))
);
GO
