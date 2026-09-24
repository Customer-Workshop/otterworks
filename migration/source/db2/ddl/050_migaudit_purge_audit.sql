-- MIGAUDIT.PURGE_AUDIT: one row per source key deleted by PURGE, inserted in the SAME unit of work
-- and BEFORE the DELETE of that key (CONTRACTS.md §9.4). Never purged, never migrated.

CREATE TABLE MIGAUDIT.PURGE_AUDIT (
    RUN_ID              VARCHAR(64)    NOT NULL,
    TABLE_NAME          VARCHAR(128)   NOT NULL,
    SOURCE_KEY          VARCHAR(64)    NOT NULL,
    PURGED_AT           TIMESTAMP(12)  NOT NULL WITH DEFAULT CURRENT TIMESTAMP,
    CONSTRAINT PK_PURGE_AUDIT PRIMARY KEY (RUN_ID, TABLE_NAME, SOURCE_KEY)
) ORGANIZE BY ROW;
