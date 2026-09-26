-- Audit-before-delete (§7): a key is written here as INTENDED before the Db2 DELETE is issued.
CREATE TABLE IF NOT EXISTS mig.purge_audit (
    run_id          VARCHAR(64)     NOT NULL,
    namespace       VARCHAR(32)     NOT NULL,
    table_name      VARCHAR(128)    NOT NULL,
    source_key      VARCHAR(64) COLLATE "C"     NOT NULL,
    batch_no        INTEGER         NOT NULL,
    status          VARCHAR(16)     NOT NULL,
    intended_at     TIMESTAMP(6)    NOT NULL,
    purged_at       TIMESTAMP(6)    NULL,
    CONSTRAINT pk_purge_audit PRIMARY KEY (run_id, namespace, table_name, source_key),
    CONSTRAINT fk_purge_audit_runs FOREIGN KEY (run_id, namespace) REFERENCES mig.runs (run_id, namespace),
    CONSTRAINT ck_purge_audit_status CHECK (status IN ('INTENDED', 'PURGED', 'ROLLED_BACK'))
);
