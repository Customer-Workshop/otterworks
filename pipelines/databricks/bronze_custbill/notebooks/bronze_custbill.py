# Databricks notebook source
# MAGIC %md
# MAGIC # bronze_custbill — CUSTBILL fixed-width feed -> Delta
# MAGIC
# MAGIC Converts the CUSTBILL leg of the nightly batch chain
# MAGIC (`sftp_ingest_poll.ksh` -> `parse_custbill_fixedwidth.sh`, copybook `CBCUST01`)
# MAGIC into a restart-safe Delta ingestion.
# MAGIC
# MAGIC The legacy parser's byte behaviour is the specification:
# MAGIC
# MAGIC * bytes 1-65 are sliced at the copybook's positions (`cut -c`, single-byte);
# MAGIC * only `CUST-ID`, `CUST-NAME` and `CURRENCY` are right-trimmed
# MAGIC   (`gsub(/ +$/,"",...)`), so `BILL-DATE`, `BILL-AMT` and `REC-TYPE` keep padding;
# MAGIC * `BILL-AMT` is `PIC 9(10)V99`: the decimal is implied, so the value is
# MAGIC   digits / 100 materialised as `DECIMAL(14,2)` (D-21) — never an integer and
# MAGIC   never a DOUBLE;
# MAGIC * `HDR`/`TRL` records are not data.
# MAGIC
# MAGIC Where this conversion deliberately diverges from the legacy job, it quarantines
# MAGIC instead of inventing a value, and records the legacy value alongside the raw
# MAGIC record so the divergence is auditable:
# MAGIC
# MAGIC | situation | legacy behaviour | here |
# MAGIC | --- | --- | --- |
# MAGIC | non-numeric `BILL-AMT` | `awk`'s `amt=$4+0` yields `0.00` | `AMT_NON_NUMERIC` |
# MAGIC | impossible `BILL-DATE` | reformatted blindly (`0000-00-00`) | `DATE_INVALID` |
# MAGIC | record < 65 bytes | `cut` pads it into empty fields | `RECORD_SHORT` |
# MAGIC | non-ASCII byte | sliced anyway, columns no longer trustworthy | `ENC_INVALID` (D-25) |
# MAGIC | record > 65 bytes | surplus silently dropped | loaded, surplus kept in `raw_overflow` |
# MAGIC | `TRL` count != detail count | logged only (ETL-0187, never implemented) | file is not ingested |
# MAGIC | file still being written | copied mid-transfer | ingested only with a matching transfer marker |
# MAGIC
# MAGIC Restart safety is `MERGE` on the natural key `(ns, source_file, record_seq)`,
# MAGIC surrogate `record_uid` = `f_md5_uuid` of that key (D-14), so a second identical
# MAGIC run is a no-op. An empty landing prefix is a normal poll outcome: the job
# MAGIC no-ops and leaves prior output intact.

# COMMAND ----------

"""Pipeline definition for the bronze_custbill unit.

This module is the single source of truth for the unit's SQL. It runs as a
Databricks notebook task in job ``ow_tp_bronze_custbill`` and is imported by
``tools/run_bronze_custbill.py``, which executes the same statements on the
serverless SQL warehouse to produce the recon evidence.
"""

from __future__ import annotations

import re

CATALOG = "ow_tp"
SCHEMA = "bronze"
UNIT = "bronze_custbill"
RECORDS_TABLE = f"{CATALOG}.{SCHEMA}.custbill_records"
QUARANTINE_TABLE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"
LANDING_ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/landing"

# Copybook CBCUST01 byte positions.
RECORD_LEN = 65
CUST_ID_POS, CUST_ID_LEN = 1, 10
CUST_NAME_POS, CUST_NAME_LEN = 11, 30
BILL_DATE_POS, BILL_DATE_LEN = 41, 8
BILL_AMT_POS, BILL_AMT_LEN = 49, 12
CURRENCY_POS, CURRENCY_LEN = 61, 3
REC_TYPE_POS, REC_TYPE_LEN = 64, 2

# Closed reason-code set (.migration/11_quarantine_codes.md) reachable from this unit.
QUARANTINE_REASONS = ("ENC_INVALID", "RECORD_SHORT", "DATE_INVALID", "AMT_NON_NUMERIC")

NS_PATTERN = re.compile(r"\A[a-z0-9_]{1,32}\Z")

# COMMAND ----------


def validate_ns(ns: str) -> str:
    """``ns`` is the isolation boundary in a shared workspace, so it is checked.

    An empty or malformed namespace is how a run reads or writes outside its own
    slice, and it is also the only value spliced into this unit's SQL text.
    """
    if not isinstance(ns, str) or not NS_PATTERN.match(ns):
        raise ValueError(
            f"ns must match {NS_PATTERN.pattern} (lowercase letters, digits, underscore; "
            f"1-32 chars); got {ns!r}"
        )
    return ns


def landing_prefix(ns: str) -> str:
    """Volume prefix this unit reads, always ``<ns>/<unit>/...``."""
    return f"{LANDING_ROOT}/{validate_ns(ns)}/custbill"


def create_records_table() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {RECORDS_TABLE} (
  ns                 STRING  NOT NULL COMMENT 'namespace this row belongs to',
  record_uid         STRING  NOT NULL COMMENT 'f_md5_uuid(ns|source_file|record_seq) (D-14)',
  source_file        STRING  NOT NULL COMMENT 'CUSTBILL drop file name',
  record_seq         BIGINT  NOT NULL COMMENT 'ordinal of the detail record within the file',
  source_file_sha256 STRING  NOT NULL COMMENT 'file identity used for partial-file protection',
  cust_id            STRING           COMMENT 'CUST-ID PIC X(10), right-trimmed as the source trims it',
  cust_name          STRING           COMMENT 'CUST-NAME PIC X(30), right-trimmed; all-space lands NULL',
  bill_date          DATE             COMMENT 'BILL-DATE PIC 9(8) YYYYMMDD, validated',
  bill_date_raw      STRING           COMMENT 'BILL-DATE bytes exactly as received, padding kept',
  bill_amt           DECIMAL(14, 2)   COMMENT 'BILL-AMT PIC 9(10)V99, implied decimal: digits/100 (D-21)',
  bill_amt_raw       STRING           COMMENT 'BILL-AMT bytes exactly as received, padding kept',
  currency           STRING           COMMENT 'CURRENCY PIC X(3), right-trimmed; all-space lands NULL',
  rec_type           STRING           COMMENT 'REC-TYPE PIC X(2), padding kept (01=invoice 02=credit)',
  null_fields        ARRAY<STRING>    COMMENT 'fields that arrived all-space and therefore landed NULL',
  raw_overflow       STRING           COMMENT 'bytes past 65 on an over-length record, never truncated away',
  overflow_flag      BOOLEAN NOT NULL COMMENT 'true when the record carried bytes past 65',
  record_bytes       INT     NOT NULL COMMENT 'byte length of the source record',
  raw_record         STRING  NOT NULL COMMENT 'the source record as received',
  payload_hash       STRING  NOT NULL COMMENT 'md5 of raw_record; MERGE only rewrites when this changes',
  ingested_at        TIMESTAMP NOT NULL
)
USING DELTA
CLUSTER BY (ns, source_file, record_seq)
COMMENT 'Bronze CUSTBILL detail records (copybook CBCUST01), one row per source detail record'
"""


def create_quarantine_table() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
  ns                 STRING  NOT NULL COMMENT 'namespace this row belongs to',
  record_uid         STRING  NOT NULL COMMENT 'f_md5_uuid(ns|source_file|record_seq) (D-14)',
  quarantine_reason  STRING  NOT NULL COMMENT 'code from .migration/11_quarantine_codes.md',
  source_table       STRING  NOT NULL COMMENT 'logical source of the row',
  source_file        STRING  NOT NULL COMMENT 'CUSTBILL drop file name',
  record_seq         BIGINT  NOT NULL COMMENT 'ordinal of the detail record within the file',
  source_file_sha256 STRING  NOT NULL COMMENT 'file identity used for partial-file protection',
  raw_record         STRING  NOT NULL COMMENT 'raw source payload, retained verbatim',
  record_bytes       INT     NOT NULL COMMENT 'byte length of the source record',
  legacy_bill_amt    DECIMAL(14, 2)   COMMENT 'value the legacy parser would have emitted (awk amt=$4+0)',
  legacy_bill_date   STRING           COMMENT 'value the legacy parser would have emitted (blind reformat)',
  payload_hash       STRING  NOT NULL COMMENT 'md5 of raw_record; MERGE only rewrites when this changes',
  quarantined_at     TIMESTAMP NOT NULL
)
USING DELTA
CLUSTER BY (ns, source_file, record_seq)
COMMENT 'Rows rejected by bronze_custbill, with the raw payload and the legacy value they diverge from'
"""


# COMMAND ----------


def _f_md5_uuid(expr: str) -> str:
    """D-14: MD5 hex laid out 8-4-4-4-12, reused verbatim from the legacy helper."""
    return (
        "concat_ws('-', "
        f"substr(lower(md5({expr})), 1, 8), substr(lower(md5({expr})), 9, 4), "
        f"substr(lower(md5({expr})), 13, 4), substr(lower(md5({expr})), 17, 4), "
        f"substr(lower(md5({expr})), 21, 12))"
    )


def parsed_source_cte(ns: str) -> str:
    """CTE chain that turns the landed drop files into classified detail records.

    Only files that are complete (byte content matches their transfer marker) and
    whose ``TRL`` count agrees with their detail-record count reach ``evaluated``.
    """
    prefix = landing_prefix(ns)
    ns = validate_ns(ns)
    uid = _f_md5_uuid("concat_ws('|', ns, source_file, cast(record_seq AS STRING))")
    return f"""
WITH raw_files AS (
  SELECT
    regexp_extract(_metadata.file_path, '([^/]+)$', 1) AS source_file,
    sha2(content, 256)                                 AS source_file_sha256,
    -- ISO-8859-1 round-trips every byte to exactly one character, so substr()
    -- addresses copybook byte positions the way the source's `cut -c` does.
    decode(content, 'ISO-8859-1')                      AS file_text
  FROM read_files('{prefix}/', format => 'binaryFile', pathGlobFilter => '*.dat')
),
transfer_markers AS (
  SELECT
    regexp_extract(_metadata.file_path, '([^/]+)\\\\.sha256$', 1) AS source_file,
    -- the marker holds the hex digest; trim() would leave the trailing newline
    lower(regexp_extract(value, '([0-9a-fA-F]{{64}})', 1))     AS declared_sha256
  FROM read_files('{prefix}/', format => 'text', wholeText => true, pathGlobFilter => '*.sha256')
),
complete_files AS (
  -- The legacy ingest has no atomic rename, so a file is only ingestible once
  -- its bytes match the marker written after the transfer completed.
  SELECT r.source_file, r.source_file_sha256, r.file_text
  FROM raw_files r
  JOIN transfer_markers m
    ON m.source_file = r.source_file
   AND m.declared_sha256 = r.source_file_sha256
),
file_lines AS (
  SELECT r.source_file, r.source_file_sha256, l.line_pos, l.raw_record
  FROM raw_files r
  LATERAL VIEW posexplode(split(r.file_text, '\\n')) l AS line_pos, raw_record
),
classified_lines AS (
  SELECT
    source_file, source_file_sha256, line_pos, raw_record,
    CASE
      WHEN raw_record LIKE 'HDR%'    THEN 'HDR'
      WHEN raw_record LIKE 'TRL%'    THEN 'TRL'
      WHEN length(raw_record) = 0    THEN 'EOF'
      ELSE 'DETAIL'
    END AS line_kind
  FROM file_lines
),
file_trailers AS (
  SELECT
    source_file,
    max(CASE WHEN line_kind = 'TRL' THEN try_cast(substr(raw_record, 4, 10) AS BIGINT) END) AS trailer_count,
    count_if(line_kind = 'DETAIL')                                                          AS detail_count
  FROM classified_lines
  GROUP BY source_file
),
ingestible_files AS (
  -- ACC-HDR-TRL: a trailer that disagrees with the detail count fails the file.
  -- ACC-PARTIAL-FILE: a file without a matching transfer marker is not ingested.
  SELECT t.source_file
  FROM file_trailers t
  JOIN (SELECT DISTINCT source_file FROM complete_files) c ON c.source_file = t.source_file
  WHERE t.trailer_count = t.detail_count
),
detail_lines AS (
  SELECT
    c.source_file, c.source_file_sha256, c.raw_record,
    row_number() OVER (PARTITION BY c.source_file ORDER BY c.line_pos) AS record_seq
  FROM classified_lines c
  JOIN ingestible_files f ON f.source_file = c.source_file
  WHERE c.line_kind = 'DETAIL'
),
parsed AS (
  SELECT
    '{ns}'                                     AS ns,
    source_file,
    record_seq,
    source_file_sha256,
    raw_record,
    length(raw_record)                         AS record_bytes,
    regexp_replace(substr(raw_record, {CUST_ID_POS}, {CUST_ID_LEN}), ' +$', '')     AS cust_id,
    regexp_replace(substr(raw_record, {CUST_NAME_POS}, {CUST_NAME_LEN}), ' +$', '') AS cust_name,
    substr(raw_record, {BILL_DATE_POS}, {BILL_DATE_LEN})                            AS bill_date_raw,
    substr(raw_record, {BILL_AMT_POS}, {BILL_AMT_LEN})                              AS bill_amt_raw,
    regexp_replace(substr(raw_record, {CURRENCY_POS}, {CURRENCY_LEN}), ' +$', '')   AS currency,
    substr(raw_record, {REC_TYPE_POS}, {REC_TYPE_LEN})                              AS rec_type,
    CASE WHEN length(raw_record) > {RECORD_LEN} THEN substr(raw_record, {RECORD_LEN} + 1) END AS raw_overflow
  FROM detail_lines
),
evaluated AS (
  SELECT
    p.*,
    {uid} AS record_uid,
    lower(md5(raw_record)) AS payload_hash,
    CASE
      -- Column positions cannot be trusted once a non-ASCII byte is present (D-25),
      -- so the encoding check precedes every field-level check.
      WHEN raw_record RLIKE '[^\\\\x00-\\\\x7F]'                     THEN 'ENC_INVALID'
      WHEN record_bytes < {RECORD_LEN}                              THEN 'RECORD_SHORT'
      WHEN NOT bill_date_raw RLIKE '^[0-9]{{{BILL_DATE_LEN}}}$'
        OR try_to_date(bill_date_raw, 'yyyyMMdd') IS NULL           THEN 'DATE_INVALID'
      WHEN NOT bill_amt_raw RLIKE '^[0-9]{{{BILL_AMT_LEN}}}$'        THEN 'AMT_NON_NUMERIC'
    END AS quarantine_reason,
    -- What the legacy parser emits for this record, kept for audit on quarantine.
    cast(
      coalesce(try_cast(regexp_extract(bill_amt_raw, '^ *([0-9]+)', 1) AS DECIMAL(20, 0)), 0) / 100
      AS DECIMAL(14, 2)
    ) AS legacy_bill_amt,
    concat_ws('-', substr(bill_date_raw, 1, 4), substr(bill_date_raw, 5, 2), substr(bill_date_raw, 7, 2))
      AS legacy_bill_date
  FROM parsed p
)
"""


def merge_records(ns: str) -> str:
    """Restart-safe load of the surviving population."""
    return f"""{parsed_source_cte(ns)}
MERGE INTO {RECORDS_TABLE} AS t
USING (
  SELECT
    ns, record_uid, source_file, record_seq, source_file_sha256,
    nullif(cust_id, '')   AS cust_id,
    nullif(cust_name, '') AS cust_name,
    to_date(bill_date_raw, 'yyyyMMdd') AS bill_date,
    bill_date_raw,
    -- D-21 implied decimal: digits / 100, DECIMAL(14,2) end to end.
    cast(cast(bill_amt_raw AS DECIMAL(20, 0)) / 100 AS DECIMAL(14, 2)) AS bill_amt,
    bill_amt_raw,
    nullif(currency, '') AS currency,
    rec_type,
    array_compact(array(
      CASE WHEN cust_id = ''   THEN 'cust_id' END,
      CASE WHEN cust_name = '' THEN 'cust_name' END,
      CASE WHEN currency = ''  THEN 'currency' END
    )) AS null_fields,
    raw_overflow,
    raw_overflow IS NOT NULL AS overflow_flag,
    record_bytes, raw_record, payload_hash
  FROM evaluated
  WHERE quarantine_reason IS NULL
) AS s
ON t.ns = s.ns AND t.record_uid = s.record_uid
WHEN MATCHED AND t.payload_hash <> s.payload_hash THEN UPDATE SET
  t.source_file = s.source_file, t.record_seq = s.record_seq,
  t.source_file_sha256 = s.source_file_sha256,
  t.cust_id = s.cust_id, t.cust_name = s.cust_name,
  t.bill_date = s.bill_date, t.bill_date_raw = s.bill_date_raw,
  t.bill_amt = s.bill_amt, t.bill_amt_raw = s.bill_amt_raw,
  t.currency = s.currency, t.rec_type = s.rec_type,
  t.null_fields = s.null_fields, t.raw_overflow = s.raw_overflow,
  t.overflow_flag = s.overflow_flag, t.record_bytes = s.record_bytes,
  t.raw_record = s.raw_record, t.payload_hash = s.payload_hash,
  t.ingested_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (
  ns, record_uid, source_file, record_seq, source_file_sha256,
  cust_id, cust_name, bill_date, bill_date_raw, bill_amt, bill_amt_raw,
  currency, rec_type, null_fields, raw_overflow, overflow_flag,
  record_bytes, raw_record, payload_hash, ingested_at
) VALUES (
  s.ns, s.record_uid, s.source_file, s.record_seq, s.source_file_sha256,
  s.cust_id, s.cust_name, s.bill_date, s.bill_date_raw, s.bill_amt, s.bill_amt_raw,
  s.currency, s.rec_type, s.null_fields, s.raw_overflow, s.overflow_flag,
  s.record_bytes, s.raw_record, s.payload_hash, current_timestamp()
)
"""


def merge_quarantine(ns: str) -> str:
    """Restart-safe capture of every rejected row, raw payload included."""
    return f"""{parsed_source_cte(ns)}
MERGE INTO {QUARANTINE_TABLE} AS t
USING (
  SELECT
    ns, record_uid, quarantine_reason,
    'CUSTBILL fixed-width drop file (copybook CBCUST01)' AS source_table,
    source_file, record_seq, source_file_sha256,
    raw_record, record_bytes,
    legacy_bill_amt, legacy_bill_date, payload_hash
  FROM evaluated
  WHERE quarantine_reason IS NOT NULL
) AS s
ON t.ns = s.ns AND t.record_uid = s.record_uid
WHEN MATCHED AND t.payload_hash <> s.payload_hash THEN UPDATE SET
  t.quarantine_reason = s.quarantine_reason, t.source_table = s.source_table,
  t.source_file = s.source_file, t.record_seq = s.record_seq,
  t.source_file_sha256 = s.source_file_sha256,
  t.raw_record = s.raw_record, t.record_bytes = s.record_bytes,
  t.legacy_bill_amt = s.legacy_bill_amt, t.legacy_bill_date = s.legacy_bill_date,
  t.payload_hash = s.payload_hash, t.quarantined_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (
  ns, record_uid, quarantine_reason, source_table, source_file, record_seq,
  source_file_sha256, raw_record, record_bytes, legacy_bill_amt, legacy_bill_date,
  payload_hash, quarantined_at
) VALUES (
  s.ns, s.record_uid, s.quarantine_reason, s.source_table, s.source_file, s.record_seq,
  s.source_file_sha256, s.raw_record, s.record_bytes, s.legacy_bill_amt, s.legacy_bill_date,
  s.payload_hash, current_timestamp()
)
"""


def load_statements(ns: str) -> list[tuple[str, str]]:
    """The unit's load, in execution order."""
    return [
        ("create_records_table", create_records_table()),
        ("create_quarantine_table", create_quarantine_table()),
        ("merge_records", merge_records(ns)),
        ("merge_quarantine", merge_quarantine(ns)),
    ]


# COMMAND ----------


def file_census(ns: str) -> str:
    """Per-file accounting straight off the landing prefix, including rejections."""
    return f"""{parsed_source_cte(ns)}
SELECT
  t.source_file,
  t.trailer_count,
  t.detail_count,
  t.trailer_count = t.detail_count AS trailer_matches,
  m.source_file IS NOT NULL        AS transfer_marker_matches
FROM (
  SELECT
    source_file,
    max(CASE WHEN line_kind = 'TRL' THEN try_cast(substr(raw_record, 4, 10) AS BIGINT) END) AS trailer_count,
    count_if(line_kind = 'DETAIL')                                                          AS detail_count
  FROM classified_lines GROUP BY source_file
) t
LEFT JOIN (SELECT DISTINCT source_file FROM complete_files) m ON m.source_file = t.source_file
ORDER BY t.source_file
"""


def source_population(ns: str) -> str:
    """Every detail record of every ingestible file, with its verdict."""
    return f"""{parsed_source_cte(ns)}
SELECT source_file, record_seq, quarantine_reason FROM evaluated ORDER BY source_file, record_seq
"""


def loaded_rows(ns: str) -> str:
    """The loaded population, recomputed from the target table."""
    ns = validate_ns(ns)
    return f"""
SELECT source_file, record_seq, cust_id, cust_name, bill_date, bill_amt, currency,
       rec_type, raw_overflow, overflow_flag, record_bytes, record_uid
FROM {RECORDS_TABLE} WHERE ns = '{ns}' ORDER BY source_file, record_seq
"""


def quarantined_rows(ns: str) -> str:
    """The quarantined population, recomputed from the target table."""
    ns = validate_ns(ns)
    return f"""
SELECT source_file, record_seq, quarantine_reason, legacy_bill_amt, legacy_bill_date,
       record_bytes, raw_record, record_uid
FROM {QUARANTINE_TABLE} WHERE ns = '{ns}' ORDER BY source_file, record_seq
"""


def target_totals(ns: str) -> str:
    """Row counts, money total and a content checksum for the idempotency proof."""
    ns = validate_ns(ns)
    return f"""
SELECT
  (SELECT count(*) FROM {RECORDS_TABLE} WHERE ns = '{ns}')                     AS loaded_rows,
  (SELECT count(*) FROM {QUARANTINE_TABLE} WHERE ns = '{ns}')                  AS quarantined_rows,
  (SELECT cast(coalesce(sum(bill_amt), 0) AS DECIMAL(20, 2))
     FROM {RECORDS_TABLE} WHERE ns = '{ns}')                                   AS bill_amt_total,
  (SELECT md5(array_join(array_sort(collect_list(concat_ws('|', record_uid, payload_hash))), ''))
     FROM {RECORDS_TABLE} WHERE ns = '{ns}')                                   AS loaded_checksum,
  (SELECT md5(array_join(array_sort(collect_list(concat_ws('|', record_uid, quarantine_reason, payload_hash))), ''))
     FROM {QUARANTINE_TABLE} WHERE ns = '{ns}')                                AS quarantine_checksum
"""


def money_column_types() -> str:
    """ACC-MONEY: every column of the unit, so a DOUBLE anywhere is visible."""
    return f"""
SELECT table_name, column_name, full_data_type
FROM {CATALOG}.information_schema.columns
WHERE table_schema = '{SCHEMA}'
  AND table_name IN ('custbill_records', 'quarantine_{UNIT}')
ORDER BY table_name, column_name
"""


# COMMAND ----------

# Notebook task entry point. Reached only on Databricks; importing the module for
# the recon runner leaves it inert.
if "dbutils" in dir():  # pragma: no cover - notebook-only path
    dbutils.widgets.text("ns", "demo")  # noqa: F821
    # Fail fast and loudly: a bad ns must not reach the volume or the SQL.
    ns = validate_ns(dbutils.widgets.get("ns"))  # noqa: F821
    prefix = landing_prefix(ns)

    try:
        landed = [f for f in dbutils.fs.ls(prefix) if f.name.endswith(".dat")]  # noqa: F821
    except Exception:  # the prefix does not exist yet: still a quiet poll
        landed = []

    print(f"{UNIT}: ns={ns} prefix={prefix} files_seen={len(landed)}")

    if not landed:
        # empty_input_semantics: no-op. Prior output stays exactly as it was.
        print(f"{UNIT}: no files present, no-op (prior output left intact)")
    else:
        for label, statement in load_statements(ns):
            print(f"{UNIT}: {label}")
            spark.sql(statement)  # noqa: F821
        totals = spark.sql(target_totals(ns)).collect()[0].asDict()  # noqa: F821
        print(f"{UNIT}: {totals}")
