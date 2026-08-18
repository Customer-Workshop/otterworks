-- ow_tp_parse_cnvparse — Databricks conversion of etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh
--
-- Contract: docs/tech-partnerships/contracts/parse_custbill_fixedwidth-cnvparse.contract.json
-- Baseline: docs/tech-partnerships/baselines/parse_custbill_fixedwidth-cnvparse.baseline.json
--
-- Single per-batch job over the namespace landing directory
-- /Volumes/ow_tp/bronze/landing/cnvparse/parse. Every object is scoped to the
-- cnvparse namespace slice; no shared/unprefixed object is created or altered.
--
-- CBCUST01 fixed-width layout (1-based columns):
--   1-10  CUST-ID   PIC X(10)      11-40 CUST-NAME PIC X(30)
--   41-48 BILL-DATE PIC 9(8)       49-60 BILL-AMT  PIC 9(10)V99 (implied decimal)
--   61-63 CURRENCY  PIC X(3)       64-65 REC-TYPE  PIC X(2) (01=invoice 02=credit)
--
-- Empty-input semantics: write-empty-result. Each run INSERT OVERWRITEs
-- bronze/silver/quarantine for this namespace from the current landing scan,
-- so a batch with no files rewrites them as empty (mirrors legacy: no
-- CUSTBILL*.dat ⇒ no PSV output; prior output does not survive).

-- ---------------------------------------------------------------------------
-- DDL: namespace-suffixed tables only (idempotent; never touches shared tables)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ow_tp.bronze.custbill_parse_raw_cnvparse (
  source_file STRING NOT NULL,
  line_no     BIGINT NOT NULL,   -- 1-based physical line number within the file
  raw_line    STRING NOT NULL,   -- exact bytes of the line (ASCII input; never re-encoded)
  rec_class   STRING NOT NULL    -- HDR | TRL | BODY (blank/short lines are BODY, as in legacy)
) USING DELTA;

CREATE TABLE IF NOT EXISTS ow_tp.silver.custbill_parsed_cnvparse (
  source_file  STRING NOT NULL,
  line_no      BIGINT NOT NULL,
  cust_id      STRING NOT NULL,   -- trailing-space-trimmed, non-blank
  cust_name    STRING NOT NULL,   -- trailing-space-trimmed
  bill_date    DATE   NOT NULL,   -- real calendar date
  amount_cents BIGINT NOT NULL,   -- 12-digit implied-decimal amount, in cents
  currency     STRING NOT NULL,   -- USD | EUR | GBP
  record_type  STRING NOT NULL    -- 01 | 02
) USING DELTA;

CREATE TABLE IF NOT EXISTS ow_tp.silver.custbill_parse_quarantine_cnvparse (
  source_file STRING NOT NULL,
  line_no     BIGINT,             -- NULL for file-level defects (trailer mismatch)
  raw_line    STRING,
  reason      STRING NOT NULL,    -- invalid_cust_id | invalid_calendar_date | nonnumeric_amount |
                                  -- unknown_currency | unknown_record_type |
                                  -- unparseable_trailer | trailer_count_mismatch
  detail      STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS ow_tp.ops.parse_expectations_cnvparse (
  expectation_id STRING NOT NULL,
  description    STRING NOT NULL,
  predicate      STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ow_tp.ops.parse_recon_runs_cnvparse (
  run_id    STRING NOT NULL,      -- deterministic: sha256 over the sorted input line set
  check_id  STRING NOT NULL,
  expected  STRING,
  actual    STRING,
  result    STRING NOT NULL       -- pass | fail | recorded (expected joined off-platform from the committed baseline)
) USING DELTA;

-- Expectation catalog (idempotent overwrite of static rows).
INSERT OVERWRITE ow_tp.ops.parse_expectations_cnvparse VALUES
  ('valid_cust_id',      'CUST-ID non-blank after trailing-space trim (PIC X(10): shorter space-padded ids are legal)', "length(rtrim(substr(raw_line,1,10))) > 0"),
  ('valid_calendar_date','BILL-DATE is 8 digits and a real calendar date',                                             "substr(raw_line,41,8) RLIKE '^[0-9]{8}$' AND try_to_date(substr(raw_line,41,8),'yyyyMMdd') IS NOT NULL"),
  ('numeric_amount',     'BILL-AMT is exactly 12 digits (PIC 9(10)V99 implied decimal)',                               "substr(raw_line,49,12) RLIKE '^[0-9]{12}$'"),
  ('known_currency',     'CURRENCY in USD/EUR/GBP after trailing-space trim',                                          "rtrim(substr(raw_line,61,3)) IN ('USD','EUR','GBP')"),
  ('known_record_type',  'REC-TYPE in 01/02',                                                                          "substr(raw_line,64,2) IN ('01','02')"),
  ('parseable_trailer',  'TRL count digits parse via try_cast (corrupted trailer never fails the job)',                "try_cast(substr(raw_line,4,10) AS BIGINT) IS NOT NULL"),
  ('trailer_reconciles', 'TRL declared count equals BODY line count (file-level; valid rows still load)',              "trailer_count = body_count");

-- ---------------------------------------------------------------------------
-- Bronze: land every line byte-for-byte (blank lines included, classed BODY)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW cnvparse_landing_lines AS
SELECT
  _metadata.file_name                                   AS source_file,
  row_number() OVER (PARTITION BY _metadata.file_name ORDER BY _metadata.file_block_start, id) AS line_no,
  value                                                 AS raw_line
FROM (
  SELECT *, monotonically_increasing_id() AS id
  FROM read_files(
    '/Volumes/ow_tp/bronze/landing/cnvparse/parse/',
    format => 'text',
    wholeText => false,
    fileNamePattern => 'CUSTBILL*.dat'
  )
);

INSERT OVERWRITE ow_tp.bronze.custbill_parse_raw_cnvparse
SELECT
  source_file,
  line_no,
  raw_line,
  CASE WHEN raw_line LIKE 'HDR%' THEN 'HDR'
       WHEN raw_line LIKE 'TRL%' THEN 'TRL'
       ELSE 'BODY' END AS rec_class
FROM cnvparse_landing_lines;

-- ---------------------------------------------------------------------------
-- Field extraction over bronze BODY records (fixed columns; a stray '|' is data)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW cnvparse_body AS
SELECT
  source_file,
  line_no,
  raw_line,
  rtrim(substr(raw_line, 1, 10))                       AS cust_id,
  rtrim(substr(raw_line, 11, 30))                      AS cust_name,
  substr(raw_line, 41, 8)                              AS bill_date_raw,
  substr(raw_line, 49, 12)                             AS amount_raw,
  rtrim(substr(raw_line, 61, 3))                       AS currency,
  substr(raw_line, 64, 2)                              AS record_type,
  try_to_date(substr(raw_line, 41, 8), 'yyyyMMdd')     AS bill_date,  -- try_* variants: ANSI mode must never fail the batch
  CASE WHEN substr(raw_line, 49, 12) RLIKE '^[0-9]{12}$'
       THEN try_cast(substr(raw_line, 49, 12) AS BIGINT) END AS amount_cents,
  -- first failing predicate, in deterministic priority order; NULL means valid
  CASE
    WHEN length(rtrim(substr(raw_line, 1, 10))) = 0                        THEN 'invalid_cust_id'
    WHEN NOT (substr(raw_line, 41, 8) RLIKE '^[0-9]{8}$')
         OR try_to_date(substr(raw_line, 41, 8), 'yyyyMMdd') IS NULL       THEN 'invalid_calendar_date'
    WHEN NOT (substr(raw_line, 49, 12) RLIKE '^[0-9]{12}$')                THEN 'nonnumeric_amount'
    WHEN rtrim(substr(raw_line, 61, 3)) NOT IN ('USD', 'EUR', 'GBP')       THEN 'unknown_currency'
    WHEN substr(raw_line, 64, 2) NOT IN ('01', '02')                       THEN 'unknown_record_type'
  END AS defect
FROM ow_tp.bronze.custbill_parse_raw_cnvparse
WHERE rec_class = 'BODY';

-- Silver admits a row only when every field predicate passes; NULL/missing
-- values never fail open into a plausible-looking row.
INSERT OVERWRITE ow_tp.silver.custbill_parsed_cnvparse
SELECT source_file, line_no, cust_id, cust_name, bill_date, amount_cents, currency, record_type
FROM cnvparse_body
WHERE defect IS NULL;

-- ---------------------------------------------------------------------------
-- Quarantine: row-level defects + file-level trailer defects
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW cnvparse_trailers AS
SELECT
  t.source_file,
  t.line_no,
  t.raw_line,
  try_cast(substr(t.raw_line, 4, 10) AS BIGINT) AS trailer_count,
  b.body_count
FROM ow_tp.bronze.custbill_parse_raw_cnvparse t
LEFT JOIN (
  SELECT source_file, count(*) AS body_count
  FROM ow_tp.bronze.custbill_parse_raw_cnvparse
  WHERE rec_class = 'BODY'
  GROUP BY source_file
) b ON b.source_file = t.source_file
WHERE t.rec_class = 'TRL';

INSERT OVERWRITE ow_tp.silver.custbill_parse_quarantine_cnvparse
SELECT source_file, line_no, raw_line, defect AS reason,
       concat('body row failed predicate ', defect) AS detail
FROM cnvparse_body
WHERE defect IS NOT NULL
UNION ALL
SELECT source_file, line_no, raw_line, 'unparseable_trailer' AS reason,
       'TRL count digits do not parse' AS detail
FROM cnvparse_trailers
WHERE trailer_count IS NULL
UNION ALL
SELECT source_file, NULL AS line_no, NULL AS raw_line, 'trailer_count_mismatch' AS reason,
       concat('trailer=', trailer_count, ' body=', coalesce(body_count, 0)) AS detail
FROM cnvparse_trailers
WHERE trailer_count IS NOT NULL
  AND trailer_count <> coalesce(body_count, 0);

-- ---------------------------------------------------------------------------
-- Recon: recompute every baseline check from the target tables
-- run_id is deterministic: sha256 over the sorted set of non-blank input lines.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TEMPORARY VIEW cnvparse_run_id AS
SELECT sha2(concat_ws('\n', sort_array(collect_list(raw_line))), 256) AS run_id
FROM ow_tp.bronze.custbill_parse_raw_cnvparse
WHERE trim(raw_line) <> '';

CREATE OR REPLACE TEMPORARY VIEW cnvparse_silver_psv AS
-- silver rows re-rendered in legacy PSV format for the file_valid_sha256 checks
SELECT
  source_file,
  concat_ws('|',
    cust_id,
    cust_name,
    date_format(bill_date, 'yyyy-MM-dd'),
    format_number(amount_cents / 100.0, '0.00'),
    currency,
    record_type
  ) AS psv_line
FROM ow_tp.silver.custbill_parsed_cnvparse;

-- Idempotent per run_id, retaining evidence of other runs: replace only this
-- batch's rows (same input bytes ⇒ same run_id ⇒ rerun rewrites its own rows).
DELETE FROM ow_tp.ops.parse_recon_runs_cnvparse
WHERE run_id IN (SELECT run_id FROM cnvparse_run_id);

INSERT INTO ow_tp.ops.parse_recon_runs_cnvparse
SELECT r.run_id, c.check_id, c.expected, c.actual,
       CASE WHEN c.expected IS NULL THEN 'recorded'
            WHEN c.expected = c.actual THEN 'pass'
            ELSE 'fail' END AS result
FROM cnvparse_run_id r
CROSS JOIN (
  SELECT concat('input_sha256/', source_file) AS check_id,
         NULL AS expected,   -- expected values are joined from the committed baseline by the recon harness
         sha2(concat_ws('\n', sort_array(collect_list(raw_line))), 256) AS actual
  FROM ow_tp.bronze.custbill_parse_raw_cnvparse
  WHERE trim(raw_line) <> ''
  GROUP BY source_file
  UNION ALL
  SELECT concat('file_valid_rows/', source_file), NULL, cast(count(*) AS STRING)
  FROM ow_tp.silver.custbill_parsed_cnvparse GROUP BY source_file
  UNION ALL
  SELECT concat('file_valid_sha256/', source_file), NULL,
         sha2(concat_ws('\n', sort_array(collect_list(psv_line))), 256)
  FROM cnvparse_silver_psv GROUP BY source_file
  UNION ALL
  SELECT concat('totals/', currency, '/', record_type), NULL,
         concat(count(*), '|', sum(amount_cents))
  FROM ow_tp.silver.custbill_parsed_cnvparse GROUP BY currency, record_type
  UNION ALL
  SELECT 'grand_total', NULL, concat(count(*), '|', sum(amount_cents))
  FROM ow_tp.silver.custbill_parsed_cnvparse
  UNION ALL
  SELECT 'files_ingested', NULL, cast(count(DISTINCT source_file) AS STRING)
  FROM ow_tp.bronze.custbill_parse_raw_cnvparse
  UNION ALL
  SELECT 'quarantine_rows', NULL, cast(count(*) AS STRING)
  FROM ow_tp.silver.custbill_parse_quarantine_cnvparse
) c;
