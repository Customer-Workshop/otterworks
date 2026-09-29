-- Key ranges = unload files; EXTRACT and LOAD restart from this table (§5 restartability).
CREATE TABLE IF NOT EXISTS mig.key_ranges (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    table_name      VARCHAR(128)    NOT NULL,
    range_seq       INTEGER         NOT NULL,
    key_from        VARCHAR(64) COLLATE "C"     NOT NULL,
    key_to          VARCHAR(64) COLLATE "C"     NOT NULL,
    rows_extracted  BIGINT          NULL,
    file_name       VARCHAR(260)    NULL,
    file_sha256     CHAR(64)        NULL,
    file_bytes      BIGINT          NULL,
    extract_status  VARCHAR(16)     NOT NULL,
    load_status     VARCHAR(16)     NOT NULL,
    extracted_at    TIMESTAMP(3)    NULL,
    loaded_at       TIMESTAMP(3)    NULL,
    CONSTRAINT pk_key_ranges PRIMARY KEY (run_id, namespace, table_name, range_seq),
    CONSTRAINT fk_key_ranges_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT ck_key_ranges_extract CHECK (extract_status IN ('PLANNED', 'RUNNING', 'DONE', 'FAILED')),
    CONSTRAINT ck_key_ranges_load CHECK (load_status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED'))
);
