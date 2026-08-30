# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_gold_finance — `finance_excel_report.pl` on Delta
# MAGIC
# MAGIC Wave 5 of the OW_BILLING → Databricks run, and the whole write path for
# MAGIC `ow_tp.gold.finance_monthly`, `ow_tp.gold.finance_report_export` and
# MAGIC `ow_tp.gold.quarantine_gold_finance`. It is a port of
# MAGIC `etl/legacy-extra/jobs/finance_excel_report.pl` together with the parser that produces
# MAGIC its input, `etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh` (copybook `CBCUST01`).
# MAGIC
# MAGIC **Which population this reads, stated first because it decides every number below.**
# MAGIC The report reads `$ROOT/parsed/CUSTBILL*.psv` — the denormalised CUSTBILL stream, landed by
# MAGIC `bronze_custbill` as `ow_tp.bronze.custbill_records`. That is the only population this unit
# MAGIC reads. It is **not** `ow_tp.silver.invoices`, and in this estate the two disagree by orders of
# MAGIC magnitude (`.migration/05_progress.md`, `ANOM-DENORM-COPIES`). A finance consumer reading
# MAGIC `ow_tp.gold.*` is reading the CUSTBILL stream, so a consumer expecting normalised invoice
# MAGIC totals sees a different number here **by design**. The recon report publishes both figures
# MAGIC side by side and reconciles neither.
# MAGIC
# MAGIC Beyond reading `ow_tp.bronze.custbill_records` and `ow_tp.bronze.quarantine_bronze_custbill`,
# MAGIC this notebook issues no statement against any table it does not own: no `INSERT`, no `UPDATE`,
# MAGIC no `DELETE`, no DDL on any bronze or silver table.
# MAGIC
# MAGIC ## What the source computes, and what happens to it here
# MAGIC
# MAGIC * **`$tot{$key} += $amt` accumulates in Perl doubles** and prints `%.2f`, so the legacy total
# MAGIC   is a binary-float sum rounded once at print (`ANOM-PERL-ROUNDING`). Money here is
# MAGIC   `DECIMAL(14,2)` end to end (`ACC-MONEY`, T1): there is no `DOUBLE` in this unit, and the
# MAGIC   float-accumulated figure is **not** reproduced in any target column. It is measured as
# MAGIC   evidence in the recon report, per group and in total, in cents.
# MAGIC * **The record-type mapping is a three-way `?:` with a live `UNKNOWN` branch**:
# MAGIC   `'01'` → `INVOICE`, `'02'` → `CREDIT`, anything else → the literal `UNKNOWN(<rt>)` carrying
# MAGIC   the raw `REC-TYPE` bytes, padding included. That string form is reproduced exactly, and an
# MAGIC   unmapped record type is a **published row**, not a reject: the source publishes it.
# MAGIC * **`next if ($cust eq "")`** — a blank `CUST-ID` skips the line silently and contributes to
# MAGIC   no group. Reproduced as a skip, and the skipped population is measured. It is not
# MAGIC   quarantined: this unit invents no reject code for a row the source deliberately drops.
# MAGIC * **`split(/\|/)` on a short line leaves trailing fields `undef`**, which then add as `0`, and
# MAGIC   `awk`'s `amt=$4+0` numifies a non-numeric amount to `0`. Neither silent zero can reach this
# MAGIC   unit: `bronze_custbill` already quarantines those records as `RECORD_SHORT` and
# MAGIC   `AMT_NON_NUMERIC` (a declared divergence, stated as one), so the populations are **measured
# MAGIC   from that unit's ledger** rather than re-detected here. The same holds for `DATE_INVALID`
# MAGIC   and `ENC_INVALID`.
# MAGIC * **Grouping and ordering.** The key is `"$ccy|$rt"` and the rows are `sort keys %tot`: a
# MAGIC   byte-wise ascending sort of the **composite** key under `LC_ALL=C`. That is not
# MAGIC   `ORDER BY currency, rec_type` — `'|'` (0x7C) sorts *after* every uppercase currency letter,
# MAGIC   so a blank-currency group lands last, where a column-wise sort would put it first. Both
# MAGIC   orders are produced and compared in the recon report rather than assumed equivalent.
# MAGIC * **There is no month filter anywhere in the script.** It reads every `CUSTBILL*.psv` in the
# MAGIC   directory and stamps only the *file name* with `localtime`, so "monthly" is a naming
# MAGIC   convention. No period predicate is invented here: `finance_monthly` is keyed on
# MAGIC   `period_month` derived from each record's own `BILL-DATE` plus `ns`, and summing every
# MAGIC   period row reproduces the legacy report's unfiltered cumulative total. Both the
# MAGIC   period-keyed shape and the reconciliation are declared divergences.
# MAGIC * **`opendir ... || die` but `open(F, ...) || next`** — an unreadable directory kills the run,
# MAGIC   an unreadable file is skipped silently. An unreadable input fails this unit loudly (the
# MAGIC   read of `ow_tp.bronze.custbill_records` is not guarded), and the number of inputs the source
# MAGIC   would have skipped is reported instead of absorbed.
# MAGIC * **The export.** The script writes CSV and `cp`s it to `.xls`. `finance_report_export`
# MAGIC   carries the CSV **content** — header `Currency,RecordType,RecordCount,TotalAmount`, `%.2f`
# MAGIC   money, the same row order — as a table, and the same bytes are written to
# MAGIC   `<export_root>/<ns>/gold_finance/finance_billing_<stamp>.csv` with a byte-identical `.xls`
# MAGIC   sibling. Mail, the lockfile and the hostname/`$ROOT` branch are deliberate
# MAGIC   non-reproductions, each with its reason in `databricks/ddl/gold_finance_spec.json`.
# MAGIC * **Empty input writes an explicit-zero report.** The legacy report over an empty parsed
# MAGIC   directory writes a CSV holding only the header. This unit does the same: the header row is
# MAGIC   published with `report_data_rows = 0`, the header-only CSV and `.xls` are written, and
# MAGIC   `finance_monthly` has no rows for the ns. It is never a no-op, so a consumer cannot read an
# MAGIC   absent report as "not run yet".
# MAGIC
# MAGIC ## PII (`ACC-NO-PII`, absolute)
# MAGIC
# MAGIC `CUSTBILL` carries `CUST-NAME`; the report's output does not. No gold target here has a
# MAGIC customer name, address or tax id column, and none has `cust_id`: the source's only use of
# MAGIC `CUST-ID` is the `eq ""` skip test, so this unit reads it as a boolean and carries neither the
# MAGIC value nor the name into gold or into the export. That also overrides the raw-payload
# MAGIC retention rule of `.migration/11_quarantine_codes.md` for this unit's quarantine table, which
# MAGIC keeps the record identity plus the non-PII fields; the raw payload stays replayable from
# MAGIC `ow_tp.bronze.*`, where it already lives under the parent-owned masks.
# MAGIC
# MAGIC ## What this notebook deletes
# MAGIC
# MAGIC Stated plainly, because a record that omits a delete is a failed review: the `MERGE` into
# MAGIC `finance_monthly` and into `finance_report_export` each carry
# MAGIC `WHEN NOT MATCHED BY SOURCE AND t.ns = <this ns> AND t._origin IN (<this unit's origins>)
# MAGIC THEN DELETE`. Both targets are this unit's own rendering of the report, so a group the current
# MAGIC population no longer contains must not stay published — the legacy report would not print it
# MAGIC either. The delete is scoped to this ns and to rows this unit wrote, it can touch no other
# MAGIC writer's row and no source-published row (D-28, D-31), and the number of rows it removes is
# MAGIC counted per run and published in the run summary. On a stable input it is 0.
# MAGIC
# MAGIC ## Order of operations
# MAGIC
# MAGIC Quarantine is persisted **before** the 5% halt is evaluated, so a halted run leaves the
# MAGIC operator its rejected rows; the halt is evaluated on one declared population (one row per
# MAGIC `ow_tp.bronze.custbill_records` row in this ns), numerator and denominator on that same
# MAGIC population; and only then is anything published. Restart safety is `MERGE` on the declared
# MAGIC key plus `ns` in every target, so a second identical run writes nothing.

# COMMAND ----------

import json
import re

# COMMAND ----------

dbutils.widgets.text("ns", "demo")
dbutils.widgets.text("catalog", "ow_tp")
dbutils.widgets.text("schema", "gold")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("export_root", "/Volumes/ow_tp/gold/exports")
dbutils.widgets.text("spec_path", "/Workspace/Shared/ow_tp/gold_finance_spec.json")
dbutils.widgets.text("batch_id", "")
# The legacy report stamps its file name with localtime. Empty means "today", which is what the
# source does; an explicit YYYYMMDD is how a deterministic replay pins the stamp.
dbutils.widgets.text("report_stamp", "")

NS = dbutils.widgets.get("ns").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRONZE = dbutils.widgets.get("bronze_schema").strip()
EXPORT_ROOT = dbutils.widgets.get("export_root").strip().rstrip("/")
SPEC_PATH = dbutils.widgets.get("spec_path").strip()
BATCH_ID = dbutils.widgets.get("batch_id").strip()
REPORT_STAMP = dbutils.widgets.get("report_stamp").strip()

UNIT = "gold_finance"

if not NS:
    raise ValueError("ns is required: every target row and every volume path is ns-scoped")
if CATALOG != "ow_tp":
    raise ValueError("this unit only reads and writes the ow_tp catalog")
if SCHEMA != "gold":
    raise ValueError("this unit owns targets in ow_tp.gold only")
if not EXPORT_ROOT.startswith(f"/Volumes/{CATALOG}/{SCHEMA}/"):
    raise ValueError(f"export_root must be a volume under {CATALOG}.{SCHEMA}; got {EXPORT_ROOT!r}")

# ns and batch_id reach SQL as literals and volume paths as path segments, so they are held to the
# estate's namespace grammar instead of being escaped ad hoc at each use site.
for _pname, _pval in (("ns", NS), ("batch_id", BATCH_ID)):
    if _pval and not re.fullmatch(r"[A-Za-z0-9_-]+", _pval):
        raise ValueError(f"{_pname}={_pval!r} must match ^[A-Za-z0-9_-]+$")
if REPORT_STAMP and not re.fullmatch(r"\d{8}", REPORT_STAMP):
    raise ValueError(f"report_stamp={REPORT_STAMP!r} must be YYYYMMDD, as the source stamps it")

if not BATCH_ID:
    BATCH_ID = spark.sql(
        "SELECT date_format(current_timestamp(), 'yyyyMMddHHmmss')"
    ).collect()[0][0]
if not REPORT_STAMP:
    REPORT_STAMP = spark.sql("SELECT date_format(current_date(), 'yyyyMMdd')").collect()[0][0]

EXPORT_DIR = f"{EXPORT_ROOT}/{NS}/{UNIT}"
CSV_PATH = f"{EXPORT_DIR}/finance_billing_{REPORT_STAMP}.csv"
XLS_PATH = f"{EXPORT_DIR}/finance_billing_{REPORT_STAMP}.xls"


def load_spec(path: str) -> dict:
    candidates = [path, f"/Workspace{path}" if not path.startswith("/Workspace") else path]
    for cand in candidates:
        try:
            with open(cand, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            continue
    raise FileNotFoundError(f"{UNIT} spec not found at any of {candidates}")


SPEC = load_spec(SPEC_PATH)

RECORD_TYPE_MAP = dict(SPEC["record_type_map"])
CSV_HEADER = SPEC["csv_header"]
MONEY_MAX_ABS = SPEC["money"]["max_abs"]
REASONS = tuple(SPEC["quarantine_reasons"])
HALT_PCT = float(SPEC["quarantine_halt_threshold_pct"])
OWNED_ORIGINS = tuple(SPEC["origins_this_unit_owns"])
SOURCE_TABLE = SPEC["source_population"]["table"]
BRONZE_QUARANTINE = SPEC["source_population"]["quarantine_ledger_read"]
SOURCE_COLUMNS_EXPECTED = tuple(SPEC["source_population"]["columns_expected"])

if RECORD_TYPE_MAP != {"01": "INVOICE", "02": "CREDIT"}:
    raise ValueError(
        "the record-type map is the source's ($rt eq '01') ? 'INVOICE' : ($rt eq '02') ? "
        "'CREDIT' : \"UNKNOWN($rt)\" — it is not configurable"
    )
if CSV_HEADER != "Currency,RecordType,RecordCount,TotalAmount":
    raise ValueError(f"csv_header must be the source's header line; got {CSV_HEADER!r}")
if UNIT != SPEC["unit"]:
    raise ValueError(f"spec is for {SPEC['unit']!r}, not {UNIT!r}")
# The reject codes below are the only ones this notebook can emit, and they are the two codes the
# spec declares. .migration/11_quarantine_codes.md is a closed set with no OTHER, so a spec that
# named a third code would mean a reject this code cannot produce or a code it cannot name.
EMITTABLE_REASONS = ("KEY_NULL", "NUMERIC_OVERFLOW")
if tuple(REASONS) != EMITTABLE_REASONS:
    raise ValueError(
        f"spec declares quarantine_reasons={REASONS}, but this unit emits exactly "
        f"{EMITTABLE_REASONS} (closed set, .migration/11_quarantine_codes.md)"
    )


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


NS_LIT = sql_str(NS)
BATCH_LIT = sql_str(BATCH_ID)
ORIGIN_LIT = sql_str(UNIT)
OWNED_ORIGINS_LIT = ", ".join(sql_str(o) for o in OWNED_ORIGINS)


def full(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"


MONTHLY = full("finance_monthly")
EXPORT = full("finance_report_export")
QUARANTINE = full("quarantine_gold_finance")
SOURCE = SOURCE_TABLE.replace("ow_tp.bronze.", f"{CATALOG}.{BRONZE}.")
SOURCE_QUARANTINE = BRONZE_QUARANTINE.replace("ow_tp.bronze.", f"{CATALOG}.{BRONZE}.")

print(f"{UNIT}: ns={NS} batch_id={BATCH_ID} report_stamp={REPORT_STAMP}")
print(f"reads {SOURCE} (read-only) -> writes {MONTHLY}, {EXPORT}, {QUARANTINE}")
print(f"export -> {CSV_PATH} (+ .xls)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## The source's shape is checked before it is read
# MAGIC
# MAGIC `malformed_record_policy.extra_delimited_fields` is `fail` in the unit contract: an undeclared
# MAGIC column arriving on the source is a schema drift nobody declared, which is a correctness event
# MAGIC rather than something to read past. This guard fails the run on any difference — added,
# MAGIC removed or renamed — between the source's column set and the set the spec declares. It says
# MAGIC nothing about column *types* and nothing about the contents of the columns; those are checked
# MAGIC where they are used.

# COMMAND ----------

source_columns = tuple(
    r[0]
    for r in spark.sql(
        f"""
SELECT column_name
FROM {CATALOG}.information_schema.columns
WHERE table_schema = {sql_str(BRONZE)} AND table_name = 'custbill_records'
ORDER BY ordinal_position
"""
    ).collect()
)
if source_columns != SOURCE_COLUMNS_EXPECTED:
    added = sorted(set(source_columns) - set(SOURCE_COLUMNS_EXPECTED))
    removed = sorted(set(SOURCE_COLUMNS_EXPECTED) - set(source_columns))
    raise RuntimeError(
        f"{SOURCE} does not have the declared column set: added={added} removed={removed} "
        f"(order seen: {list(source_columns)}). The unit contract's malformed_record_policy "
        "fails on undeclared source drift instead of ignoring it."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Targets
# MAGIC
# MAGIC Money is `DECIMAL(14,2)` in every target. There is deliberately no float column anywhere:
# MAGIC the legacy accumulator's binary-float behaviour is evidence in the recon report, not a value
# MAGIC a consumer should be able to read out of gold.

# COMMAND ----------

spark.sql(
    f"""
CREATE TABLE IF NOT EXISTS {MONTHLY} (
  ns               STRING  NOT NULL COMMENT 'namespace this row belongs to',
  period_month     STRING  NOT NULL COMMENT "period derived from the record's own BILL-DATE, yyyy-MM (the legacy report has no month filter)",
  legacy_group_key STRING  NOT NULL COMMENT 'the source grouping key "$ccy|$rt", byte-sorted in the report',
  currency         STRING           COMMENT 'CURRENCY as bronze holds it: NULL where the source field was all-space',
  rec_type         STRING  NOT NULL COMMENT 'REC-TYPE bytes as received, padding kept',
  record_type      STRING  NOT NULL COMMENT "the report's label: INVOICE, CREDIT, or UNKNOWN(<rec_type>)",
  record_count     BIGINT  NOT NULL COMMENT 'rows in the group (%d of $cnt{{$key}})',
  total_amount     DECIMAL(14, 2) NOT NULL COMMENT 'exact decimal sum of BILL-AMT for the group (T1)',
  period_row_seq   INT     NOT NULL COMMENT 'position of the group in byte order within this period',
  source_population STRING NOT NULL COMMENT 'the population this figure was computed from',
  _origin          STRING  NOT NULL COMMENT 'unit that wrote the row',
  _batch_id        STRING  NOT NULL,
  _updated_at      TIMESTAMP NOT NULL
)
USING DELTA
CLUSTER BY (ns, period_month, legacy_group_key)
COMMENT 'Finance billing totals by currency and record type, keyed by the period each record carries (gold_finance, wave 5)'
"""
)

spark.sql(
    f"""
CREATE TABLE IF NOT EXISTS {EXPORT} (
  ns                STRING  NOT NULL COMMENT 'namespace this row belongs to',
  line_kind         STRING  NOT NULL COMMENT 'header or data',
  legacy_group_key  STRING  NOT NULL COMMENT 'the source grouping key "$ccy|$rt"; HEADER on the header line',
  row_seq           INT     NOT NULL COMMENT 'line position in the CSV, 0 = header, then byte order of the key',
  currency          STRING           COMMENT 'CURRENCY as bronze holds it: NULL where the source field was all-space',
  rec_type          STRING           COMMENT 'REC-TYPE bytes as received, padding kept',
  record_type       STRING           COMMENT "the report's label: INVOICE, CREDIT, or UNKNOWN(<rec_type>)",
  record_count      BIGINT           COMMENT 'rows in the group, cumulative over every period (the report has no month filter)',
  total_amount      DECIMAL(14, 2)   COMMENT 'exact decimal sum of BILL-AMT for the group (T1)',
  total_amount_text STRING           COMMENT 'the amount as the report prints it (%.2f)',
  csv_line          STRING  NOT NULL COMMENT 'the CSV line itself, byte for byte as exported',
  report_data_rows  BIGINT           COMMENT 'data lines in this report; set on the header row, 0 for an empty report',
  export_csv_path   STRING  NOT NULL COMMENT 'volume path the same bytes were written to',
  export_xls_path   STRING  NOT NULL COMMENT 'the .xls copy the source makes with cp',
  report_stamp      STRING  NOT NULL COMMENT 'YYYYMMDD stamp in the exported file name',
  _origin           STRING  NOT NULL COMMENT 'unit that wrote the row',
  _batch_id         STRING  NOT NULL,
  _updated_at       TIMESTAMP NOT NULL
)
USING DELTA
CLUSTER BY (ns, row_seq)
COMMENT 'The finance report CSV content, one row per exported line, in the order the legacy report writes them (gold_finance, wave 5)'
"""
)

spark.sql(
    f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE} (
  ns                STRING  NOT NULL COMMENT 'namespace this row belongs to',
  record_uid        STRING  NOT NULL COMMENT 'the bronze record identity this reject came from (D-14)',
  quarantine_reason STRING  NOT NULL COMMENT 'code from .migration/11_quarantine_codes.md',
  source_table      STRING  NOT NULL COMMENT 'logical source of the row',
  source_file       STRING           COMMENT 'CUSTBILL drop file the record came from',
  record_seq        BIGINT           COMMENT 'ordinal of the record within that file',
  bill_date         DATE             COMMENT 'BILL-DATE as bronze holds it',
  bill_amt          DECIMAL(14, 2)   COMMENT 'BILL-AMT as bronze holds it',
  currency          STRING           COMMENT 'CURRENCY as bronze holds it',
  rec_type          STRING           COMMENT 'REC-TYPE bytes as received',
  legacy_group_key  STRING           COMMENT 'the group this row would have joined',
  detail            STRING  NOT NULL COMMENT 'why the row was rejected, in words',
  _origin           STRING  NOT NULL COMMENT 'unit that wrote the row',
  _batch_id         STRING  NOT NULL,
  quarantined_at    TIMESTAMP NOT NULL
)
USING DELTA
CLUSTER BY (ns, record_uid)
COMMENT 'Rows gold_finance refused to publish. No raw payload and no PII by ACC-NO-PII: the payload stays in ow_tp.bronze.custbill_records under the parent-owned masks'
"""
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## The report, as the source computes it
# MAGIC
# MAGIC `v_source` selects no `cust_id` and no `cust_name`: `CUST-ID` is read only as the boolean the
# MAGIC source's `next if ($cust eq "")` tests, and `CUST-NAME` is never read at all.

# COMMAND ----------

spark.sql(
    f"""
CREATE OR REPLACE TEMPORARY VIEW v_source AS
SELECT
  record_uid,
  source_file,
  record_seq,
  bill_date,
  bill_amt,
  currency,
  rec_type,
  (cust_id IS NULL OR cust_id = '') AS blank_customer
FROM {SOURCE}
WHERE ns = {NS_LIT}
"""
)

spark.sql(
    f"""
CREATE OR REPLACE TEMPORARY VIEW v_judged AS
SELECT
  s.*,
  concat(coalesce(s.currency, ''), '|', s.rec_type) AS legacy_group_key,
  date_format(s.bill_date, 'yyyy-MM')               AS period_month,
  CASE
    WHEN s.rec_type IS NULL THEN 'KEY_NULL'
    WHEN s.bill_date IS NULL THEN 'KEY_NULL'
  END AS row_reason
FROM v_source s
"""
)

# The cumulative figure the report prints is what has to fit DECIMAL(14,2): a period that fits on
# its own while the report total does not is still unpublishable, and D-23/T6 forbid widening the
# type or rounding to make it fit. Judged on the group the source would print, in exact decimal.
spark.sql(
    f"""
CREATE OR REPLACE TEMPORARY VIEW v_group_overflow AS
SELECT legacy_group_key
FROM v_judged
WHERE row_reason IS NULL AND NOT blank_customer
GROUP BY legacy_group_key
HAVING abs(cast(sum(bill_amt) AS DECIMAL(38, 2))) > cast({MONEY_MAX_ABS} AS DECIMAL(38, 2))
"""
)

spark.sql(
    """
CREATE OR REPLACE TEMPORARY VIEW v_rows AS
SELECT
  j.*,
  CASE
    WHEN j.row_reason IS NOT NULL THEN j.row_reason
    WHEN o.legacy_group_key IS NOT NULL THEN 'NUMERIC_OVERFLOW'
  END AS quarantine_reason
FROM v_judged j
LEFT JOIN v_group_overflow o ON o.legacy_group_key = j.legacy_group_key
"""
)

spark.sql(
    """
CREATE OR REPLACE TEMPORARY VIEW v_published_rows AS
SELECT * FROM v_rows WHERE quarantine_reason IS NULL AND NOT blank_customer
"""
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quarantine first, then the halt, then publish
# MAGIC
# MAGIC In that order: a halted run has to leave the operator its rejected rows, and the threshold is
# MAGIC evaluated on one declared population — one row per `ow_tp.bronze.custbill_records` row in this
# MAGIC ns — with the numerator taken from that same population.
# MAGIC
# MAGIC Every `MERGE` below gates its `WHEN MATCHED ... UPDATE` on a value change (`<=>` per column),
# MAGIC so a rerun over an unchanged population writes no row and Delta's own metrics say so. The
# MAGIC export **file** is rewritten unconditionally with the same bytes — a run must not leave an
# MAGIC absent report — so file-level idempotency is asserted on content, not on absence of a write.

# COMMAND ----------

quarantine_merge = f"""
MERGE INTO {QUARANTINE} AS t
USING (
  SELECT
    {NS_LIT} AS ns,
    record_uid,
    quarantine_reason,
    {sql_str(SOURCE_TABLE)} AS source_table,
    source_file,
    record_seq,
    bill_date,
    bill_amt,
    currency,
    rec_type,
    legacy_group_key,
    CASE quarantine_reason
      WHEN 'KEY_NULL' THEN 'REC-TYPE or BILL-DATE is NULL, so neither the group key "$ccy|$rt" nor the period is derivable and the row cannot be made idempotent'
      WHEN 'NUMERIC_OVERFLOW' THEN concat('the cumulative total of group ', legacy_group_key, ' does not fit DECIMAL(14,2); D-23/T6 forbid widening the type or rounding to fit, so every row of the group is withheld')
    END AS detail
  FROM v_rows
  WHERE quarantine_reason IS NOT NULL
) AS s
ON t.ns = s.ns AND t.record_uid = s.record_uid
-- Gated on a value change so a rerun over an unchanged population is a true no-op in Delta's own
-- metrics: an ungated UPDATE SET would rewrite _batch_id on every matched row and report a
-- non-zero numTargetRowsUpdated for a run that changed nothing.
WHEN MATCHED AND NOT (
  t.quarantine_reason <=> s.quarantine_reason AND t.source_table <=> s.source_table
  AND t.source_file <=> s.source_file AND t.record_seq <=> s.record_seq
  AND t.bill_date <=> s.bill_date AND t.bill_amt <=> s.bill_amt
  AND t.currency <=> s.currency AND t.rec_type <=> s.rec_type
  AND t.legacy_group_key <=> s.legacy_group_key AND t.detail <=> s.detail
) THEN UPDATE SET
  t.quarantine_reason = s.quarantine_reason, t.source_table = s.source_table,
  t.source_file = s.source_file, t.record_seq = s.record_seq,
  t.bill_date = s.bill_date, t.bill_amt = s.bill_amt, t.currency = s.currency,
  t.rec_type = s.rec_type, t.legacy_group_key = s.legacy_group_key, t.detail = s.detail,
  t._origin = {ORIGIN_LIT}, t._batch_id = {BATCH_LIT}, t.quarantined_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (
  ns, record_uid, quarantine_reason, source_table, source_file, record_seq,
  bill_date, bill_amt, currency, rec_type, legacy_group_key, detail,
  _origin, _batch_id, quarantined_at
) VALUES (
  s.ns, s.record_uid, s.quarantine_reason, s.source_table, s.source_file, s.record_seq,
  s.bill_date, s.bill_amt, s.currency, s.rec_type, s.legacy_group_key, s.detail,
  {ORIGIN_LIT}, {BATCH_LIT}, current_timestamp()
)
"""
spark.sql(quarantine_merge)

population = spark.sql(
    """
SELECT
  count(*)                                              AS source_rows,
  count_if(quarantine_reason IS NOT NULL)               AS quarantined_rows,
  count_if(quarantine_reason IS NULL AND blank_customer) AS blank_customer_skips,
  count_if(quarantine_reason IS NULL AND NOT blank_customer) AS contributing_rows
FROM v_rows
"""
).collect()[0]
SOURCE_ROWS = int(population["source_rows"])
QUARANTINED_ROWS = int(population["quarantined_rows"])
BLANK_SKIPS = int(population["blank_customer_skips"])
CONTRIBUTING_ROWS = int(population["contributing_rows"])
QUARANTINE_RATE = (100.0 * QUARANTINED_ROWS / SOURCE_ROWS) if SOURCE_ROWS else 0.0

print(
    f"declared population {SOURCE_ROWS} rows of {SOURCE} (ns={NS}): "
    f"{CONTRIBUTING_ROWS} contributing + {BLANK_SKIPS} blank-customer skips + "
    f"{QUARANTINED_ROWS} quarantined; quarantine {QUARANTINE_RATE:.2f}% of {SOURCE_ROWS}"
)
if QUARANTINE_RATE > HALT_PCT:
    raise RuntimeError(
        f"STOPA-QUARANTINE: {QUARANTINED_ROWS} of {SOURCE_ROWS} rows quarantined "
        f"({QUARANTINE_RATE:.2f}% > {HALT_PCT}%) on the declared population "
        f"({SOURCE} ns={NS}). The rejected rows are persisted in {QUARANTINE} for triage; "
        "nothing was published."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## `finance_monthly` — one row per period and group
# MAGIC
# MAGIC The period comes from each record's own `BILL-DATE`; the legacy report filters on nothing, so
# MAGIC the reconciliation is `sum(total_amount) over every period == the legacy report's own total`,
# MAGIC proven in the recon report rather than asserted here.

# COMMAND ----------

spark.sql(
    """
CREATE OR REPLACE TEMPORARY VIEW v_monthly AS
SELECT
  period_month,
  legacy_group_key,
  max(currency)                        AS currency,
  max(rec_type)                        AS rec_type,
  count(*)                             AS record_count,
  cast(sum(bill_amt) AS DECIMAL(14, 2)) AS total_amount,
  cast(
    row_number() OVER (PARTITION BY period_month ORDER BY legacy_group_key ASC) AS INT
  )                                    AS period_row_seq
FROM v_published_rows
GROUP BY period_month, legacy_group_key
"""
)

monthly_merge = f"""
MERGE INTO {MONTHLY} AS t
USING (
  SELECT
    {NS_LIT} AS ns,
    period_month,
    legacy_group_key,
    currency,
    rec_type,
    CASE rec_type
      WHEN '01' THEN 'INVOICE'
      WHEN '02' THEN 'CREDIT'
      ELSE concat('UNKNOWN(', rec_type, ')')
    END AS record_type,
    record_count,
    total_amount,
    period_row_seq,
    {sql_str(SOURCE_TABLE)} AS source_population
  FROM v_monthly
) AS s
ON t.ns = s.ns AND t.period_month = s.period_month AND t.legacy_group_key = s.legacy_group_key
WHEN MATCHED AND NOT (
  t.currency <=> s.currency AND t.rec_type <=> s.rec_type AND t.record_type <=> s.record_type
  AND t.record_count <=> s.record_count AND t.total_amount <=> s.total_amount
  AND t.period_row_seq <=> s.period_row_seq AND t.source_population <=> s.source_population
) THEN UPDATE SET
  t.currency = s.currency, t.rec_type = s.rec_type, t.record_type = s.record_type,
  t.record_count = s.record_count, t.total_amount = s.total_amount,
  t.period_row_seq = s.period_row_seq, t.source_population = s.source_population,
  t._origin = {ORIGIN_LIT}, t._batch_id = {BATCH_LIT}, t._updated_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (
  ns, period_month, legacy_group_key, currency, rec_type, record_type,
  record_count, total_amount, period_row_seq, source_population,
  _origin, _batch_id, _updated_at
) VALUES (
  s.ns, s.period_month, s.legacy_group_key, s.currency, s.rec_type, s.record_type,
  s.record_count, s.total_amount, s.period_row_seq, s.source_population,
  {ORIGIN_LIT}, {BATCH_LIT}, current_timestamp()
)
WHEN NOT MATCHED BY SOURCE AND t.ns = {NS_LIT} AND t._origin IN ({OWNED_ORIGINS_LIT}) THEN DELETE
"""
spark.sql(monthly_merge)

# COMMAND ----------

# MAGIC %md
# MAGIC ## `finance_report_export` — the CSV the source writes
# MAGIC
# MAGIC `sort keys %tot` is a byte-wise ascending sort of the composite key: Spark's `ORDER BY` on a
# MAGIC `STRING` compares UTF-8 bytes, which is the same order `LC_ALL=C` gives the legacy `sort`.
# MAGIC The recon report proves that on the data rather than trusting it, and publishes the
# MAGIC column-wise order beside it to show the two differ. `total_amount_text` is the `DECIMAL(14,2)`
# MAGIC rendered as text — always two decimals, and never via a float.

# COMMAND ----------

spark.sql(
    """
CREATE OR REPLACE TEMPORARY VIEW v_report AS
SELECT
  legacy_group_key,
  max(currency)                        AS currency,
  max(rec_type)                        AS rec_type,
  count(*)                             AS record_count,
  cast(sum(bill_amt) AS DECIMAL(14, 2)) AS total_amount
FROM v_published_rows
GROUP BY legacy_group_key
"""
)

spark.sql(
    f"""
CREATE OR REPLACE TEMPORARY VIEW v_export_lines AS
WITH data_lines AS (
  SELECT
    'data' AS line_kind,
    legacy_group_key,
    cast(row_number() OVER (ORDER BY legacy_group_key ASC) AS INT) AS row_seq,
    currency,
    rec_type,
    CASE rec_type
      WHEN '01' THEN 'INVOICE'
      WHEN '02' THEN 'CREDIT'
      ELSE concat('UNKNOWN(', rec_type, ')')
    END AS record_type,
    record_count,
    total_amount,
    cast(total_amount AS STRING) AS total_amount_text
  FROM v_report
)
SELECT
  'header' AS line_kind,
  'HEADER'  AS legacy_group_key,
  0         AS row_seq,
  cast(NULL AS STRING) AS currency,
  cast(NULL AS STRING) AS rec_type,
  cast(NULL AS STRING) AS record_type,
  cast(NULL AS BIGINT) AS record_count,
  cast(NULL AS DECIMAL(14, 2)) AS total_amount,
  cast(NULL AS STRING) AS total_amount_text,
  {sql_str(CSV_HEADER)} AS csv_line,
  (SELECT count(*) FROM data_lines) AS report_data_rows
UNION ALL
SELECT
  line_kind, legacy_group_key, row_seq, currency, rec_type, record_type,
  record_count, total_amount, total_amount_text,
  -- concat, not concat_ws: concat_ws drops a NULL argument and would silently shift the
  -- remaining columns left, turning a missing field into a wrong one.
  concat(coalesce(currency, ''), ',', record_type, ',', cast(record_count AS STRING), ',', total_amount_text) AS csv_line,
  cast(NULL AS BIGINT) AS report_data_rows
FROM data_lines
"""
)

export_merge = f"""
MERGE INTO {EXPORT} AS t
USING (
  SELECT
    {NS_LIT} AS ns,
    line_kind, legacy_group_key, row_seq, currency, rec_type, record_type,
    record_count, total_amount, total_amount_text, csv_line, report_data_rows,
    {sql_str(CSV_PATH)} AS export_csv_path,
    {sql_str(XLS_PATH)} AS export_xls_path,
    {sql_str(REPORT_STAMP)} AS report_stamp
  FROM v_export_lines
) AS s
ON t.ns = s.ns AND t.line_kind = s.line_kind AND t.legacy_group_key = s.legacy_group_key
WHEN MATCHED AND NOT (
  t.row_seq <=> s.row_seq AND t.currency <=> s.currency AND t.rec_type <=> s.rec_type
  AND t.record_type <=> s.record_type AND t.record_count <=> s.record_count
  AND t.total_amount <=> s.total_amount AND t.total_amount_text <=> s.total_amount_text
  AND t.csv_line <=> s.csv_line AND t.report_data_rows <=> s.report_data_rows
  AND t.export_csv_path <=> s.export_csv_path AND t.export_xls_path <=> s.export_xls_path
  AND t.report_stamp <=> s.report_stamp
) THEN UPDATE SET
  t.row_seq = s.row_seq, t.currency = s.currency, t.rec_type = s.rec_type,
  t.record_type = s.record_type, t.record_count = s.record_count,
  t.total_amount = s.total_amount, t.total_amount_text = s.total_amount_text,
  t.csv_line = s.csv_line, t.report_data_rows = s.report_data_rows,
  t.export_csv_path = s.export_csv_path, t.export_xls_path = s.export_xls_path,
  t.report_stamp = s.report_stamp,
  t._origin = {ORIGIN_LIT}, t._batch_id = {BATCH_LIT}, t._updated_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (
  ns, line_kind, legacy_group_key, row_seq, currency, rec_type, record_type,
  record_count, total_amount, total_amount_text, csv_line, report_data_rows,
  export_csv_path, export_xls_path, report_stamp, _origin, _batch_id, _updated_at
) VALUES (
  s.ns, s.line_kind, s.legacy_group_key, s.row_seq, s.currency, s.rec_type, s.record_type,
  s.record_count, s.total_amount, s.total_amount_text, s.csv_line, s.report_data_rows,
  s.export_csv_path, s.export_xls_path, s.report_stamp, {ORIGIN_LIT}, {BATCH_LIT}, current_timestamp()
)
WHEN NOT MATCHED BY SOURCE AND t.ns = {NS_LIT} AND t._origin IN ({OWNED_ORIGINS_LIT}) THEN DELETE
"""
spark.sql(export_merge)

# COMMAND ----------

# MAGIC %md
# MAGIC ## The exported file
# MAGIC
# MAGIC The same bytes the table carries, in the same order, terminated the way Perl's `print`
# MAGIC terminates each line, plus the byte-identical `.xls` copy the source makes with `cp`. Written
# MAGIC on every run, including a run with no input rows: an empty report is a header-only file, not a
# MAGIC missing one.

# COMMAND ----------

export_rows = spark.sql(
    f"""
SELECT csv_line FROM {EXPORT} WHERE ns = {NS_LIT} ORDER BY row_seq
"""
).collect()
csv_bytes = "".join(f"{r['csv_line']}\n" for r in export_rows).encode("utf-8")

dbutils.fs.mkdirs(EXPORT_DIR)
dbutils.fs.put(CSV_PATH, csv_bytes.decode("utf-8"), overwrite=True)
dbutils.fs.put(XLS_PATH, csv_bytes.decode("utf-8"), overwrite=True)
print(f"wrote {len(export_rows)} lines ({len(csv_bytes)} bytes) to {CSV_PATH} and {XLS_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run summary
# MAGIC
# MAGIC Everything the run measured, written beside the export so the recon can compare the notebook's
# MAGIC own account of the run against figures it recomputes from the targets itself.

# COMMAND ----------

def merge_metrics(table: str) -> dict:
    row = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]
    metrics = row["operationMetrics"] or {}
    return {
        "version": int(row["version"]),
        "operation": row["operation"],
        "rows_inserted": int(metrics.get("numTargetRowsInserted", 0)),
        "rows_updated": int(metrics.get("numTargetRowsUpdated", 0)),
        "rows_deleted": int(metrics.get("numTargetRowsDeleted", 0)),
    }


measured = spark.sql(
    """
SELECT
  count_if(NOT blank_customer AND quarantine_reason IS NULL AND rec_type NOT IN ('01', '02')) AS unknown_rec_type_rows,
  count_if(blank_customer)                                       AS blank_customer_skips,
  count_if(quarantine_reason IS NOT NULL)                        AS quarantined_rows,
  count(DISTINCT CASE WHEN NOT blank_customer AND quarantine_reason IS NULL AND rec_type NOT IN ('01', '02') THEN rec_type END) AS unknown_rec_type_codes,
  count(DISTINCT coalesce(currency, ''))                         AS currencies,
  count_if(currency IS NULL)                                     AS null_currency_rows,
  count(DISTINCT source_file)                                    AS source_files_represented
FROM v_rows
"""
).collect()[0]

# The source skips an input it cannot open and says nothing (`open(F, ...) || next`). This unit has no
# equivalent silent skip — an unreadable source read fails the run — so the count the source would
# have skipped is reported instead: every file bronze_custbill refused for this ns, by reason.
files_bronze_refused = [
    {"source_file": r[0], "rows": int(r[1]), "reasons": r[2]}
    for r in spark.sql(
        f"""
SELECT source_file, count(*), array_join(array_sort(collect_set(quarantine_reason)), ',')
FROM {SOURCE_QUARANTINE}
WHERE ns = {NS_LIT}
  AND source_file NOT IN (SELECT DISTINCT source_file FROM {SOURCE} WHERE ns = {NS_LIT})
GROUP BY source_file ORDER BY source_file
"""
    ).collect()
]

summary = {
    "unit": UNIT,
    "ns": NS,
    "batch_id": BATCH_ID,
    "report_stamp": REPORT_STAMP,
    "source_population": SOURCE_TABLE,
    "source_quarantine_ledger": SOURCE_QUARANTINE,
    "accounting": {
        "source_rows": SOURCE_ROWS,
        "contributing_rows": CONTRIBUTING_ROWS,
        "blank_customer_skips": BLANK_SKIPS,
        "quarantined_rows": QUARANTINED_ROWS,
        "identity": (
            f"{CONTRIBUTING_ROWS} contributing + {BLANK_SKIPS} blank-customer skips + "
            f"{QUARANTINED_ROWS} quarantined == {SOURCE_ROWS} source rows"
        ),
        "quarantine_rate_pct": round(QUARANTINE_RATE, 4),
        "quarantine_halt_threshold_pct": HALT_PCT,
        "halt_population": SPEC["declared_population_for_the_halt"],
    },
    "measured_populations": {
        "unknown_record_type_rows": int(measured["unknown_rec_type_rows"]),
        "unknown_record_type_codes": int(measured["unknown_rec_type_codes"]),
        "blank_customer_skips": int(measured["blank_customer_skips"]),
        "currencies": int(measured["currencies"]),
        "null_currency_rows": int(measured["null_currency_rows"]),
        "source_files_represented": int(measured["source_files_represented"]),
        "files_wholly_refused_upstream": files_bronze_refused,
    },
    "export": {
        "csv_path": CSV_PATH,
        "xls_path": XLS_PATH,
        "lines": len(export_rows),
        "bytes": len(csv_bytes),
        "data_rows": len(export_rows) - 1,
        "empty_report": len(export_rows) == 1,
    },
    "merge_metrics": {
        "finance_monthly": merge_metrics(MONTHLY),
        "finance_report_export": merge_metrics(EXPORT),
        "quarantine_gold_finance": merge_metrics(QUARANTINE),
    },
    "rows_by_period": [
        {"period_month": r[0], "groups": int(r[1]), "record_count": int(r[2]), "total_amount": str(r[3])}
        for r in spark.sql(
            f"""
            SELECT period_month, count(*), sum(record_count), cast(sum(total_amount) AS DECIMAL(20, 2))
            FROM {MONTHLY} WHERE ns = {NS_LIT} GROUP BY period_month ORDER BY period_month
            """
        ).collect()
    ],
    "report": [
        {
            "row_seq": int(r[0]),
            "csv_line": r[1],
            "legacy_group_key": r[2],
            "record_count": None if r[3] is None else int(r[3]),
            "total_amount": None if r[4] is None else str(r[4]),
        }
        for r in spark.sql(
            f"""
            SELECT row_seq, csv_line, legacy_group_key, record_count, total_amount
            FROM {EXPORT} WHERE ns = {NS_LIT} ORDER BY row_seq
            """
        ).collect()
    ],
}

out_path = f"{EXPORT_DIR}/_runs/{BATCH_ID}.json"
dbutils.fs.mkdirs(f"{EXPORT_DIR}/_runs")
dbutils.fs.put(out_path, json.dumps(summary, indent=1), overwrite=True)
print(f"run summary -> {out_path}")
dbutils.notebook.exit(json.dumps({"run_summary": out_path, "batch_id": BATCH_ID}))
