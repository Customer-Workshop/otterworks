-- ARCHIVE.DOCARCH: archived document versions (unit of move; parent of FILEAUD). Logical layout: DOCARCH.cpy, LRECL 256.
-- Db2 -> Oracle:
--   CHAR(n) FOR BIT DATA -> RAW(n)      OWNER_NAME keeps its cp037 bytes incl. the undefined 0xFF (MIG-01);
--                                       DISPOSITION_DT keeps LOW-VALUES x'00' (MIG-03) and 'YYYYMMDD' text.
--   DECIMAL(31,8)        -> NUMBER(31,8) unconstrained precision on the source; the target's DECIMAL(19,8) is
--                                       what MIG-02 overflows.
--   TIMESTAMP(12)        -> TIMESTAMP(9) Oracle keeps 9 fraction digits; the driver re-pads to the 12-digit text.
--   BIGINT / SMALLINT    -> NUMBER(19) / NUMBER(5)
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE TABLE ARCHIVE.DOCARCH (
    ARCH_KEY            CHAR(16)       NOT NULL,
    DOC_ID              CHAR(36)       NOT NULL,
    VERSION_NO          NUMBER(5)      NOT NULL,
    RETENTION_CLASS     CHAR(4)        NOT NULL,
    LAST_ACCESS_TS      TIMESTAMP(9)   NOT NULL,
    STORAGE_CHARGE      NUMBER(31,8)   NOT NULL,
    UNIT_RATE           NUMBER(31,8)   NOT NULL,
    OWNER_NAME          RAW(40)        NOT NULL,
    DISPOSITION_DT      RAW(8)         NOT NULL,
    LEGAL_HOLD_FLAG     CHAR(1)        NOT NULL,
    CHECKSUM_ALG        CHAR(8)        NOT NULL,
    CONTENT_SHA256      CHAR(64)       NOT NULL,
    BYTE_SIZE           NUMBER(19)     NOT NULL,
    SOURCE_SYS          CHAR(3)        NOT NULL,
    CONSTRAINT PK_DOCARCH PRIMARY KEY (ARCH_KEY),
    CONSTRAINT FK_DOCARCH_RETNPLCY FOREIGN KEY (RETENTION_CLASS) REFERENCES ARCHIVE.RETNPLCY (POLICY_CODE),
    CONSTRAINT CK_DOCARCH_HOLD CHECK (LEGAL_HOLD_FLAG IN ('Y', 'N'))
);

-- Selection predicate index: RETENTION_CLASS IN (...) AND LAST_ACCESS_TS < cutoff.
CREATE INDEX ARCHIVE.IX_DOCARCH_SELECT ON ARCHIVE.DOCARCH (RETENTION_CLASS, LAST_ACCESS_TS);
