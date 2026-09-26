-- Per-row VALIDATE verdicts (§6). purge_safe can only be true for VALIDATED rows.
CREATE TABLE IF NOT EXISTS mig.validation (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    table_name      VARCHAR(128)    NOT NULL,
    source_key      VARCHAR(64) COLLATE "C"     NOT NULL,
    source_hash     BYTEA           NOT NULL,
    target_hash     BYTEA           NULL,
    status          VARCHAR(16)     NOT NULL,
    rule_name       VARCHAR(64)     NULL,
    purge_safe      BOOLEAN         NOT NULL,
    validated_at    TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT pk_validation PRIMARY KEY (run_id, namespace, table_name, source_key),
    CONSTRAINT fk_validation_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT ck_validation_status CHECK (status IN ('VALIDATED', 'FAILED')),
    CONSTRAINT ck_validation_safe CHECK (purge_safe = FALSE OR status = 'VALIDATED')
);

-- Class-level row counts and charge sums on both sides (§6.3 class totals).
CREATE TABLE IF NOT EXISTS mig.class_totals (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    table_name      VARCHAR(128)    NOT NULL,
    class_code      VARCHAR(8)      NOT NULL,
    side            VARCHAR(6)      NOT NULL,
    row_count       BIGINT          NOT NULL,
    charge_sum      NUMERIC(38, 8)  NULL,
    CONSTRAINT pk_class_totals PRIMARY KEY (run_id, namespace, table_name, class_code, side),
    CONSTRAINT fk_class_totals_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT ck_class_totals_side CHECK (side IN ('SOURCE', 'TARGET'))
);
