# Field derivation: DOCARCH copybook

`DOCARCH.cpy` arrived with no comments and terse field names (`DA-RCLS`, `DA-LACC`, `DA-SCHG`,
`DA-FLG1`, ...). The copybook is **not** edited to add meaning; meaning is derived from the Db2
catalog plus data profiling and recorded here and in the manifest `field_map`
(`migration/manifest.yaml` -> `tables[DOCARCH].copybook.field_map`). The job reads the
`field_map`, never this document.

The same method applies to `FILEAUD.cpy` and `RETNPLCY.cpy`; their names are less terse, so only the
result table is given for them (end of this file).

## 1. Method

### Step 1 - physical layout from the copybook

Lay out every elementary item with its byte offset and length (GnuCOBOL defaults: `COMP` is
big-endian two's complement sized 2/4/8 bytes by digit count; `COMP-3` is packed decimal,
`ceil((digits + 1) / 2)` bytes, sign nibble `C`/`F` positive, `D` negative).

```bash
cobc -x -free -fsyntax-only ...   # or simply the table below
```

### Step 2 - candidate columns from SYSCAT

```sql
SELECT COLNO, COLNAME, TYPENAME, LENGTH, SCALE, CODEPAGE, NULLS, KEYSEQ
FROM   SYSCAT.COLUMNS
WHERE  TABSCHEMA = 'ARCHIVE' AND TABNAME = 'DOCARCH'
ORDER  BY COLNO;

SELECT CONSTNAME, TYPE FROM SYSCAT.TABCONST  WHERE TABSCHEMA = 'ARCHIVE' AND TABNAME = 'DOCARCH';
SELECT CONSTNAME, FK_COLNAMES, REFTABNAME FROM SYSCAT.REFERENCES
WHERE  TABSCHEMA = 'ARCHIVE' AND TABNAME IN ('DOCARCH', 'FILEAUD');
SELECT CONSTNAME, TEXT FROM SYSCAT.CHECKS WHERE TABSCHEMA = 'ARCHIVE' AND TABNAME = 'DOCARCH';
```

Match rule, applied in order; a field is bound only when **all** hold:

1. Ordinal: the n-th non-`FILLER` elementary item is paired with `COLNO = n - 1`.
2. Width: copybook byte length equals the column's external width
   (`CHAR(n)` -> n; `SMALLINT` -> 2; `BIGINT` -> 8; `DECIMAL(p,s)` -> `ceil((p+1)/2)` with
   `V9(s)` equal to `SCALE`; `TIMESTAMP(12)` -> `PIC X(32)`).
3. Class: `PIC X` pairs only with `CHAR`/`TIMESTAMP`; `COMP` only with integer types; `COMP-3` only
   with `DECIMAL`.
4. Profiling (step 3) does not contradict the pairing.

`CODEPAGE = 0` on a `CHAR` column means `FOR BIT DATA`: Db2 stores bytes without conversion, so
the real encoding must come from profiling.

### Step 3 - data profiling

Run against the seeded Db2 database (or an UNLOAD file) with the profiler the job unit ships
(`python -m ldm profile` is optional; the SQL below is sufficient):

```sql
-- cardinality / shape per column (repeat per column)
SELECT COUNT(*), COUNT(DISTINCT RETENTION_CLASS), MIN(RETENTION_CLASS), MAX(RETENTION_CLASS)
FROM ARCHIVE.DOCARCH;
-- byte histogram of a FOR BIT DATA column (first byte shown; repeat for positions 1..40)
SELECT HEX(SUBSTR(OWNER_NAME, 1, 1)) AS B, COUNT(*) FROM ARCHIVE.DOCARCH GROUP BY HEX(SUBSTR(OWNER_NAME, 1, 1));
-- trailing padding byte of a FOR BIT DATA column
SELECT HEX(SUBSTR(OWNER_NAME, 40, 1)) AS PAD, COUNT(*) FROM ARCHIVE.DOCARCH GROUP BY HEX(SUBSTR(OWNER_NAME, 40, 1));
-- domain of a 1-byte flag
SELECT LEGAL_HOLD_FLAG, COUNT(*) FROM ARCHIVE.DOCARCH GROUP BY LEGAL_HOLD_FLAG;
-- referential role
SELECT COUNT(*) FROM ARCHIVE.DOCARCH D WHERE NOT EXISTS
  (SELECT 1 FROM ARCHIVE.RETNPLCY P WHERE P.POLICY_CODE = D.RETENTION_CLASS);
```

Profiling evidence that decides encoding:

- EBCDIC 037: pad byte `X'40'` in >99% of rows; letters in `X'C1'-X'C9'`, `X'D1'-X'D9'`,
  `X'E2'-X'E9'`; digits in `X'F0'-X'F9'`; no bytes in `X'20'-X'7E'` except `X'40'`, `X'4B'` (.),
  `X'6B'` (,), `X'60'` (-), `X'7D'` (').
- Low-values `X'00'` repeated across a whole field is the COBOL "no value" convention, not data.

## 2. Result: DOCARCH (LRECL 256)

Offsets are 1-based and inclusive; `Len` is bytes in the fixed-width record.

| # | Copybook | PIC | Off | Len | Db2 column (COLNO) | Db2 type | Derived meaning | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | `DA-AKEY` | `X(16)` | 1 | 16 | `ARCH_KEY` (0) | `CHAR(16)` | Archive record key (PK). `DA` + 14 digits; reserved `MIGnn-...` keys for planted cases | `SYSCAT.TABCONST` P constraint, `KEYSEQ=1`; 100% distinct |
| 2 | `DA-DOCI` | `X(36)` | 17 | 36 | `DOC_ID` (1) | `CHAR(36)` | OtterWorks document UUID (links to the app's document) | 8-4-4-4-12 hex pattern in 100% of rows |
| 3 | `DA-VSEQ` | `S9(4) COMP` | 53 | 2 | `VERSION_NO` (2) | `SMALLINT` | Document version number, 1..n per `DOC_ID` | min 1; dense per `DOC_ID` |
| 4 | `DA-RCLS` | `X(4)` | 55 | 4 | `RETENTION_CLASS` (3) | `CHAR(4)` | Retention class code | FK to `RETNPLCY.POLICY_CODE`; 35 distinct values in use |
| 5 | `DA-LACC` | `X(32)` | 59 | 32 | `LAST_ACCESS_TS` (4) | `TIMESTAMP(12)` | Last access time, picosecond precision | text `YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN`; >= 2012-01-01 |
| 6 | `DA-SCHG` | `S9(23)V9(8) COMP-3` | 91 | 16 | `STORAGE_CHARGE` (5) | `DECIMAL(31,8)` | Accrued storage charge (currency, 8 dp) | non-negative; sums reconcile to billing |
| 7 | `DA-AMT2` | `S9(23)V9(8) COMP-3` | 107 | 16 | `UNIT_RATE` (6) | `DECIMAL(31,8)` | Per-byte-month storage rate | < 1 in >99.99% of rows; outliers are MIG-02 |
| 8 | `DA-TXT1` | `X(40)` | 123 | 40 | `OWNER_NAME` (7) | `CHAR(40) FOR BIT DATA` | Owner display name, **EBCDIC CCSID 037** | `CODEPAGE=0`; pad `X'40'`; letter bytes `X'C1'-X'E9'` |
| 9 | `DA-DAT1` | `X(8)` | 163 | 8 | `DISPOSITION_DT` (8) | `CHAR(8) FOR BIT DATA` | Scheduled disposition date `YYYYMMDD`, **EBCDIC 037 digits** | bytes only `X'F0'-X'F9'` or all `X'00'` (low-values) |
| 10 | `DA-FLG1` | `X` | 171 | 1 | `LEGAL_HOLD_FLAG` (9) | `CHAR(1)` | Legal hold indicator | domain `{'Y','N'}` via `SYSCAT.CHECKS` |
| 11 | `DA-CD01` | `X(8)` | 172 | 8 | `CHECKSUM_ALG` (10) | `CHAR(8)` | Content checksum algorithm | single value `SHA256` (padded) |
| 12 | `DA-HSH1` | `X(64)` | 180 | 64 | `CONTENT_SHA256` (11) | `CHAR(64)` | Hex SHA-256 of the stored document bytes | `[0-9a-f]{64}` |
| 13 | `DA-CNT1` | `S9(18) COMP` | 244 | 8 | `BYTE_SIZE` (12) | `BIGINT` | Document size in bytes | positive; correlates with `STORAGE_CHARGE / UNIT_RATE` |
| 14 | `DA-SRC` | `X(3)` | 252 | 3 | `SOURCE_SYS` (13) | `CHAR(3)` | Originating system code | domain `{'OWD','OWF','IMP'}` |
| - | `FILLER` | `X(2)` | 255 | 2 | - | - | Unused; written as spaces `X'20'` | - |

Byte check: 16+36+2+4+32+16+16+40+8+1+8+64+8+3+2 = **256**.

## 3. Result: FILEAUD (LRECL 160)

| # | Copybook | PIC | Off | Len | Db2 column | Db2 type |
|---|---|---|---|---|---|---|
| 1 | `FA-AUD-KEY` | `X(20)` | 1 | 20 | `AUDIT_KEY` | `CHAR(20)` |
| 2 | `FA-ARCH-KEY` | `X(16)` | 21 | 16 | `ARCH_KEY` | `CHAR(16)` |
| 3 | `FA-EVT-TYPE` | `X(4)` | 37 | 4 | `EVENT_TYPE` | `CHAR(4)` |
| 4 | `FA-EVT-TS` | `X(32)` | 41 | 32 | `EVENT_TS` | `TIMESTAMP(12)` |
| 5 | `FA-ACTOR` | `X(12)` | 73 | 12 | `ACTOR_ID` | `CHAR(12)` |
| 6 | `FA-RET-CLASS` | `X(4)` | 85 | 4 | `RETENTION_CLASS` | `CHAR(4)` |
| 7 | `FA-DISP-CD` | `X(2)` | 89 | 2 | `DISPOSITION_CODE` | `CHAR(2)` |
| 8 | `FA-CLIENT-IP` | `X(15)` | 91 | 15 | `CLIENT_IP` | `CHAR(15)` |
| 9 | `FA-DETAIL` | `X(40)` | 106 | 40 | `DETAIL_TEXT` | `CHAR(40)` |
| - | `FILLER` | `X(15)` | 146 | 15 | - | - |

Byte check: 20+16+4+32+12+4+2+15+40+15 = **160**.

## 4. Result: RETNPLCY (LRECL 128)

| # | Copybook | PIC | Off | Len | Db2 column | Db2 type |
|---|---|---|---|---|---|---|
| 1 | `RP-POLICY-CD` | `X(4)` | 1 | 4 | `POLICY_CODE` | `CHAR(4)` |
| 2 | `RP-POLICY-DESC` | `X(60)` | 5 | 60 | `POLICY_DESC` | `CHAR(60)` |
| 3 | `RP-RET-YEARS` | `S9(4) COMP` | 65 | 2 | `RETENTION_YEARS` | `SMALLINT` |
| 4 | `RP-SUCCESSOR-CD` | `X(4)` | 67 | 4 | `SUCCESSOR_CODE` | `CHAR(4)` (all blanks = active, no successor) |
| 5 | `RP-ACTIVE-FLG` | `X` | 71 | 1 | `ACTIVE_FLAG` | `CHAR(1)` |
| 6 | `RP-DISP-ACTION` | `X(4)` | 72 | 4 | `DISPOSITION_ACTION` | `CHAR(4)` |
| 7 | `RP-EFFECTIVE-TS` | `X(32)` | 76 | 32 | `EFFECTIVE_TS` | `TIMESTAMP(12)` |
| - | `FILLER` | `X(21)` | 108 | 21 | - | - |

Byte check: 4+60+2+4+1+4+32+21 = **128**.

## 5. Encoding rules shared by all three layouts

- Every field of every record is present; there are no null indicators (all columns are `NOT NULL`).
- `PIC X` over a non-`FOR BIT DATA` column: ASCII/UTF-8 single-byte characters, right-padded with
  `X'20'`.
- `PIC X` over a `FOR BIT DATA` column: raw bytes exactly as stored in Db2 (EBCDIC 037 for
  `OWNER_NAME`, `DISPOSITION_DT`), right-padded with `X'40'` by the writer of the row.
- `TIMESTAMP(12)` as `PIC X(32)`: `YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN` in ASCII.
- `COMP`: big-endian two's complement (`SMALLINT` 2 bytes, `BIGINT` 8 bytes).
- `COMP-3`: 31 digit nibbles + 1 sign nibble = 16 bytes; sign `X'C'` (writers) / `X'C'` or `X'F'`
  (readers accept) positive, `X'D'` negative.
- `FILLER`: spaces `X'20'`; readers ignore the content.
- Records are concatenated with **no** line terminator (RECFM=F).
