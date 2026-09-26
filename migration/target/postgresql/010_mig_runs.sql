-- One row per run per namespace; status transitions in CONTRACTS.md §5.
CREATE TABLE IF NOT EXISTS mig.runs (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    status          VARCHAR(16)     NOT NULL,
    purge_enabled   BOOLEAN         NOT NULL,
    manifest_sha256 CHAR(64)        NULL,
    job_image       VARCHAR(256)    NULL,
    started_at      TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    finished_at     TIMESTAMP(3)    NULL,
    exit_code       INTEGER         NULL,
    closes          BOOLEAN         NULL,
    CONSTRAINT pk_runs PRIMARY KEY (run_id, namespace),
    CONSTRAINT ck_runs_status CHECK (status IN ('RUNNING', 'CLOSED', 'FAILED', 'ABANDONED'))
);

-- Devin session links rendered by report-service (§10).
CREATE TABLE IF NOT EXISTS mig.run_sessions (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    ordinal         INTEGER         NOT NULL,
    label           VARCHAR(128)    NOT NULL,
    url             VARCHAR(512)    NOT NULL,
    CONSTRAINT pk_run_sessions PRIMARY KEY (run_id, namespace, ordinal),
    CONSTRAINT fk_run_sessions_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace)
);
