#!/usr/bin/env python3
"""SQL for the converted CUSTBILL fixed-width parser (unit parse_custbill_fixedwidth).

The legacy job (etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh) slices
copybook CBCUST01 with cut, divides the implied decimal in awk, reformats the
date with substr and no validity check, and logs the trailer count without
comparing it. This module is its silver replacement: typed columns, declared
expectations stored as data (ow_tp.ops.parse_expectations_<ns>), and an
expectation-based quarantine where every rejected record carries the
expectation id it violated and its raw source line.

Copybook CBCUST01 layout (65 bytes):
  1-10 CUST-ID, 11-40 CUST-NAME, 41-48 BILL-DATE YYYYMMDD,
  49-60 BILL-AMT PIC 9(10)V99 implied decimal, 61-63 CURRENCY, 64-65 REC-TYPE
"""
from __future__ import annotations

from dataclasses import dataclass

RECORD_LENGTH = 65


@dataclass(frozen=True)
class ParseNames:
    catalog: str = "ow_tp"
    ns: str = "w2parse"

    @property
    def landing(self) -> str:
        return f"/Volumes/{self.catalog}/bronze/landing/{self.ns}"

    @property
    def feed_dir(self) -> str:
        return f"{self.landing}/parse_custbill"

    @property
    def bronze(self) -> str:
        return f"{self.catalog}.bronze.custbill_parse_raw_{self.ns}"

    @property
    def silver(self) -> str:
        return f"{self.catalog}.silver.custbill_records_{self.ns}"

    @property
    def quarantine(self) -> str:
        return f"{self.catalog}.silver.custbill_quarantine_{self.ns}"

    @property
    def expectations(self) -> str:
        return f"{self.catalog}.ops.parse_expectations_{self.ns}"

    @property
    def parse_runs(self) -> str:
        return f"{self.catalog}.ops.parse_runs_{self.ns}"


# Declared expectations, loaded into ow_tp.ops.parse_expectations_<ns> and read
# back from the table to generate the parse SQL: the table is the source of
# truth, not this constant. Reason classes for the anomaly kinds the history
# manifest plants keep the manifest's names (invalid_calendar_date,
# nonnumeric_amount, trailer_count_mismatch) so recon set-compares without a
# mapping layer; the classes the manifest does not plant follow the contract's
# names. Priority is first-violation-wins for records carrying several defects.
EXPECTATIONS = [
    # (id, scope, field, reason_class, rule, violation_predicate, priority)
    ("EXP-LEN", "record", "raw_line", "record_length_mismatch",
     f"record is exactly {RECORD_LENGTH} bytes as declared by copybook CBCUST01",
     f"length(raw_line) <> {RECORD_LENGTH}", 10),
    ("EXP-ENC", "record", "raw_line", "undecodable_bytes",
     "record contains only printable single-byte ASCII (the declared encoding)",
     "raw_line RLIKE '[^ -~]'", 20),
    ("EXP-DATE", "record", "bill_date", "invalid_calendar_date",
     "BILL-DATE is a valid YYYYMMDD calendar date",
     "try_to_date(bill_date_raw, 'yyyyMMdd') IS NULL", 30),
    ("EXP-AMT", "record", "bill_amt", "nonnumeric_amount",
     "BILL-AMT is 12 numeric digits (PIC 9(10)V99)",
     "NOT amount_raw RLIKE '^[0-9]{12}$'", 40),
    ("EXP-CCY", "record", "currency", "unknown_currency",
     "CURRENCY is in the declared whitelist USD/EUR/GBP",
     "currency NOT IN ('USD', 'EUR', 'GBP')", 50),
    ("EXP-RT", "record", "record_type", "unknown_record_type",
     "REC-TYPE is in the declared domain 01 (invoice) / 02 (credit)",
     "record_type NOT IN ('01', '02')", 60),
    ("EXP-TRL", "file", "trailer", "trailer_count_mismatch",
     "TRL trailer count equals the number of body records (ETL-0187)",
     "coalesce(trailer_count, -1) <> body_count", 70),
]


def provision(n: ParseNames) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS {n.bronze} (
              source_file STRING COMMENT 'CUSTBILL extract file name as dropped',
              source_feed STRING COMMENT 'seed (clean drop) or history (2019-2024 backfill feed)',
              source_period STRING COMMENT 'YYYYMM billing period when the name carries one',
              source_year INT,
              line_no INT COMMENT '1-based physical line number within the file',
              record_kind STRING COMMENT 'HDR, TRL or BODY',
              raw_line STRING COMMENT 'Untouched fixed-width record',
              ingested_at TIMESTAMP)
            USING DELTA
            COMMENT 'Bronze: byte-preserved CUSTBILL drops, one row per line (input of record)'""",
        f"""CREATE OR REPLACE TABLE {n.silver} (
              cust_id STRING, cust_name STRING,
              bill_date DATE COMMENT 'Real DATE, validity enforced by EXP-DATE',
              amount DECIMAL(12,2) COMMENT 'PIC 9(10)V99 implied decimal, cents-exact',
              amount_cents BIGINT,
              currency STRING, record_type STRING COMMENT 'source code 01/02',
              record_class STRING COMMENT 'INVOICE (01) / CREDIT (02)',
              source_file STRING, source_feed STRING, source_period STRING,
              source_year INT, record_offset INT COMMENT 'line number in the source file')
            USING DELTA
            COMMENT 'Silver: validated CUSTBILL billing records (quarantined rows excluded)'""",
        f"""CREATE OR REPLACE TABLE {n.quarantine} (
              source_file STRING, source_feed STRING, source_period STRING, source_year INT,
              record_offset INT COMMENT 'line number in the source file; 0 for file-scope defects',
              cust_id STRING,
              expectation_id STRING COMMENT 'id in ow_tp.ops.parse_expectations the record violated',
              reason_class STRING,
              raw_line STRING COMMENT 'raw source line of the rejected record',
              detected_at TIMESTAMP)
            USING DELTA
            COMMENT 'Silver: records the legacy parser passed through silently, with the violated expectation'""",
        f"""CREATE TABLE IF NOT EXISTS {n.expectations} (
              expectation_id STRING, scope STRING COMMENT 'record or file',
              field STRING, reason_class STRING,
              rule STRING COMMENT 'human-readable declaration',
              violation_predicate STRING COMMENT 'SQL predicate over the parsed projection that flags a violation',
              priority INT COMMENT 'first-violation-wins order for records with several defects')
            USING DELTA
            COMMENT 'Declared parse expectations as data; the parse SQL is generated from these rows'""",
        f"""CREATE TABLE IF NOT EXISTS {n.parse_runs} (
              source_file STRING, source_feed STRING, source_period STRING, source_year INT,
              body_records BIGINT, trailer_count BIGINT,
              silver_rows BIGINT, quarantined_rows BIGINT,
              status STRING COMMENT 'ok, or failed when the trailer disagrees with the body count',
              parsed_at TIMESTAMP)
            USING DELTA
            COMMENT 'Per-file parse outcome; an empty file is a records=0 row, an absent file is absent'""",
    ]


def load_expectations(n: ParseNames) -> str:
    # Spark treats '' inside a literal as adjacent-literal concatenation, so
    # embedded quotes must be backslash-escaped.
    esc = lambda s: s.replace("\\", "\\\\").replace("'", "\\'")
    rows = ",\n".join(
        f"('{i}', '{scope}', '{field}', '{reason}', '{esc(rule)}', '{esc(pred)}', {prio})"
        for i, scope, field, reason, rule, pred, prio in EXPECTATIONS
    )
    return (f"INSERT OVERWRITE {n.expectations} "
            f"(expectation_id, scope, field, reason_class, rule, violation_predicate, priority) "
            f"VALUES\n{rows}")


def load_bronze(n: ParseNames, feed: str, path: str, replace_feed: bool) -> list[str]:
    statements = []
    if replace_feed:
        statements.append(f"DELETE FROM {n.bronze} WHERE source_feed = '{feed}'")
    statements.append(f"""
    INSERT INTO {n.bronze}
    SELECT
      regexp_extract(_metadata.file_path, '([^/]+)$', 1) AS source_file,
      '{feed}' AS source_feed,
      nullif(regexp_extract(_metadata.file_path, 'CUSTBILL_[A-Z0-9_-]+_([0-9]{{6}})\\\\.dat$', 1), '') AS source_period,
      try_cast(substr(regexp_extract(_metadata.file_path, 'CUSTBILL_[A-Z0-9_-]+_([0-9]{{6}})\\\\.dat$', 1), 1, 4) AS INT) AS source_year,
      CAST(row_number() OVER (PARTITION BY _metadata.file_path ORDER BY monotonically_increasing_id()) AS INT) AS line_no,
      CASE WHEN startswith(value, 'HDR') THEN 'HDR'
           WHEN startswith(value, 'TRL') THEN 'TRL'
           ELSE 'BODY' END AS record_kind,
      value AS raw_line,
      current_timestamp() AS ingested_at
    FROM read_files('{path}', format => 'text', recursiveFileLookup => true)""")
    return statements


def line_number_invariant(n: ParseNames) -> str:
    """The bronze line numbers come from a window over monotonically_increasing_id,
    so they are verified rather than assumed: every file must have its HDR at
    line 1 and its TRL at the last line."""
    return f"""
    SELECT source_file,
           min(CASE WHEN record_kind = 'HDR' THEN line_no END) AS hdr_line,
           max(CASE WHEN record_kind = 'TRL' THEN line_no END) AS trl_line,
           max(line_no) AS last_line,
           count(*) AS lines
    FROM {n.bronze}
    GROUP BY source_file
    HAVING hdr_line IS DISTINCT FROM 1
        OR trl_line IS DISTINCT FROM last_line
        OR lines <> last_line"""


def body_projection(n: ParseNames) -> str:
    return f"""
      SELECT
        source_file, source_feed, source_period, source_year, line_no,
        trim(substr(raw_line, 1, 10)) AS cust_id,
        trim(substr(raw_line, 11, 30)) AS cust_name,
        substr(raw_line, 41, 8) AS bill_date_raw,
        substr(raw_line, 49, 12) AS amount_raw,
        trim(substr(raw_line, 61, 3)) AS currency,
        substr(raw_line, 64, 2) AS record_type,
        raw_line
      FROM {n.bronze}
      WHERE record_kind = 'BODY'"""


def _record_cases(record_expectations: list[dict]) -> tuple[str, str]:
    ordered = sorted(record_expectations, key=lambda e: int(e["priority"]))
    id_case = "CASE " + " ".join(
        f"WHEN {e['violation_predicate']} THEN '{e['expectation_id']}'" for e in ordered
    ) + " END"
    reason_case = "CASE " + " ".join(
        f"WHEN {e['violation_predicate']} THEN '{e['reason_class']}'" for e in ordered
    ) + " END"
    return id_case, reason_case


def _violations(n: ParseNames, record_expectations: list[dict]) -> str:
    id_case, reason_case = _record_cases(record_expectations)
    return f"""
      SELECT *, {id_case} AS expectation_id, {reason_case} AS reason_class
      FROM ({body_projection(n)})"""


def build_silver(n: ParseNames, record_expectations: list[dict]) -> str:
    return f"""
    INSERT OVERWRITE {n.silver}
    SELECT cust_id, cust_name,
           to_date(bill_date_raw, 'yyyyMMdd') AS bill_date,
           CAST(CAST(amount_raw AS DECIMAL(12,0)) / 100 AS DECIMAL(12,2)) AS amount,
           CAST(amount_raw AS BIGINT) AS amount_cents,
           currency, record_type,
           CASE record_type WHEN '01' THEN 'INVOICE' WHEN '02' THEN 'CREDIT' END AS record_class,
           source_file, source_feed, source_period, source_year, line_no AS record_offset
    FROM ({_violations(n, record_expectations)})
    WHERE expectation_id IS NULL"""


def file_counts(n: ParseNames) -> str:
    return f"""
      SELECT source_file, source_feed, source_period, source_year,
             count_if(record_kind = 'BODY') AS body_count,
             max(CASE WHEN record_kind = 'TRL' THEN try_cast(substr(raw_line, 4, 10) AS BIGINT) END) AS trailer_count,
             max(CASE WHEN record_kind = 'TRL' THEN raw_line END) AS trailer_line
      FROM {n.bronze}
      GROUP BY source_file, source_feed, source_period, source_year"""


def build_quarantine(n: ParseNames, record_expectations: list[dict], file_expectation: dict) -> str:
    return f"""
    INSERT OVERWRITE {n.quarantine}
    SELECT source_file, source_feed, source_period, source_year,
           line_no AS record_offset, cust_id, expectation_id, reason_class, raw_line,
           current_timestamp() AS detected_at
    FROM ({_violations(n, record_expectations)})
    WHERE expectation_id IS NOT NULL
    UNION ALL
    SELECT source_file, source_feed, source_period, source_year,
           0 AS record_offset, '' AS cust_id,
           '{file_expectation['expectation_id']}' AS expectation_id,
           '{file_expectation['reason_class']}' AS reason_class,
           coalesce(trailer_line, '<missing TRL record>') AS raw_line,
           current_timestamp() AS detected_at
    FROM ({file_counts(n)})
    WHERE {file_expectation['violation_predicate']}"""


def build_parse_runs(n: ParseNames, file_expectation: dict) -> str:
    return f"""
    INSERT OVERWRITE {n.parse_runs}
    SELECT f.source_file, f.source_feed, f.source_period, f.source_year,
           f.body_count, f.trailer_count,
           coalesce(s.silver_rows, 0), coalesce(q.quarantined_rows, 0),
           CASE WHEN {file_expectation['violation_predicate']} THEN 'failed' ELSE 'ok' END AS status,
           current_timestamp() AS parsed_at
    FROM ({file_counts(n)}) f
    LEFT JOIN (SELECT source_file, count(*) AS silver_rows FROM {n.silver} GROUP BY source_file) s
      ON f.source_file = s.source_file
    LEFT JOIN (SELECT source_file, count(*) AS quarantined_rows FROM {n.quarantine} GROUP BY source_file) q
      ON f.source_file = q.source_file"""


def parse_gate(n: ParseNames) -> str:
    """Trailer reconciliation enforced, not logged (PRS-04 / ETL-0187): a run over
    input whose trailer disagrees with its body count fails the SQL task,
    naming the files and their counts."""
    return f"""
    WITH failed AS (
      SELECT concat(source_file, ' trailer=', CAST(trailer_count AS STRING),
                    ' body=', CAST(body_records AS STRING)) AS msg
      FROM {n.parse_runs} WHERE status = 'failed'
    )
    SELECT CASE WHEN (SELECT count(*) FROM failed) > 0
                THEN raise_error(concat('PARSE FAILED: trailer_count_mismatch on ',
                     CAST((SELECT count(*) FROM failed) AS STRING), ' file(s): ',
                     (SELECT concat_ws('; ', slice(collect_list(msg), 1, 12)) FROM failed)))
                ELSE concat('PARSE GREEN: ', CAST((SELECT count(*) FROM {n.parse_runs}) AS STRING),
                     ' file(s) parsed, ',
                     CAST((SELECT count(*) FROM {n.quarantine}) AS STRING), ' record(s) quarantined')
           END AS parse_result"""
