-- Mirror of the PostgreSQL control plane written by the job at promotion / run close (never the source of truth).
CREATE TABLE IF NOT EXISTS MIG.RUNS (
    RUN_ID          VARCHAR(64)         NOT NULL,
    NAMESPACE       VARCHAR(32)         NOT NULL,
    STATUS          VARCHAR(16)         NOT NULL,
    PURGE_ENABLED   BOOLEAN             NULL,
    EXIT_CODE       INTEGER             NULL,
    CLOSES          BOOLEAN             NULL,
    FINISHED_AT     TIMESTAMP_NTZ(3)    NULL,
    CONSTRAINT PK_RUNS PRIMARY KEY (RUN_ID, NAMESPACE)
);

CREATE TABLE IF NOT EXISTS MIG.RUN_LEDGER (
    RUN_ID          VARCHAR(64)         NOT NULL,
    NAMESPACE       VARCHAR(32)         NOT NULL,
    TABLE_NAME      VARCHAR(128)        NOT NULL,
    TABLE_ORDER     INTEGER             NOT NULL,
    TABLE_ROLE      VARCHAR(16)         NOT NULL,
    EXTRACTED       BIGINT              NULL,
    EXTRACT_FILES   INTEGER             NULL,
    LOADED          BIGINT              NULL,
    REJECTED        BIGINT              NULL,
    VALIDATED       BIGINT              NULL,
    VALIDATE_FAILED BIGINT              NULL,
    PURGE_INTENDED  BIGINT              NULL,
    PURGED          BIGINT              NULL,
    PURGE_DRY_RUN   BOOLEAN             NULL,
    CONSTRAINT PK_RUN_LEDGER PRIMARY KEY (RUN_ID, NAMESPACE, TABLE_NAME)
);

-- Per-row verdicts (§6); the promotion INSERT ... SELECT joins STG.<table> to this table.
CREATE TABLE IF NOT EXISTS MIG.VALIDATION (
    RUN_ID          VARCHAR(64)         NOT NULL,
    NAMESPACE       VARCHAR(32)         NOT NULL,
    TABLE_NAME      VARCHAR(128)        NOT NULL,
    SOURCE_KEY      VARCHAR(64)         NOT NULL,
    SOURCE_HASH     BINARY(32)          NOT NULL,
    TARGET_HASH     BINARY(32)          NULL,
    STATUS          VARCHAR(16)         NOT NULL,
    RULE_NAME       VARCHAR(64)         NULL,
    PURGE_SAFE      BOOLEAN             NOT NULL,
    VALIDATED_AT    TIMESTAMP_NTZ(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ(3),
    CONSTRAINT PK_VALIDATION PRIMARY KEY (RUN_ID, NAMESPACE, TABLE_NAME, SOURCE_KEY)
);
