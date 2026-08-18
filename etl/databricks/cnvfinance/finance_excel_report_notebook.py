# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_finance_cnvfinance — finance report (converted from finance_excel_report.pl)
# MAGIC
# MAGIC Per-batch (manual trigger, `max_concurrent_runs=1`), namespace-sliced, idempotent
# MAGIC by (ns, report_date) slice replacement.
# MAGIC Contract: `docs/tech-partnerships/contracts/finance_excel_report-cnvfinance.contract.json`.
# MAGIC
# MAGIC What the legacy job did and what replaced it:
# MAGIC - CSV renamed to `.xls` → a truthful `.csv` artifact, byte-identical grid,
# MAGIC   written to the namespace volume and verified by read-back digest
# MAGIC - silent sendmail pipe → a delivery record in
# MAGIC   `ow_tp.gold.finance_report_delivery_cnvfinance` that records verified
# MAGIC   volume delivery and the explicit absence of a mail transport
# MAGIC - hostname branching, /tmp lock file → `ns`/`report_date` job parameters

# COMMAND ----------

import os
import re
import sys

dbutils.widgets.text("ns", "cnvfinance")
dbutils.widgets.text("report_date", "2026-01-15")
NS = dbutils.widgets.get("ns")
REPORT_DATE = dbutils.widgets.get("report_date")

notebook_dir = os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
)
sys.path.append(f"/Workspace{notebook_dir}")
from finance_core import (  # noqa: E402
    ParsedBatch,
    deterministic_run_id,
    is_report_input,
    parse_legacy_report_csv,
    parse_psv_bytes,
    render_report_csv,
    require_ns,
    sha256_hex,
)

require_ns(NS)
if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", REPORT_DATE):
    raise ValueError(f"report_date must be YYYY-MM-DD: {REPORT_DATE!r}")
STAMP = REPORT_DATE.replace("-", "")

CATALOG = "ow_tp"
ROOT = f"/Volumes/{CATALOG}/bronze/landing/{NS}/finance_report"
PARSED_DIR = f"{ROOT}/parsed"
REPORTS_DIR = f"{ROOT}/reports"
LEGACY_DIR = f"{ROOT}/legacy"
SILVER_TABLE = f"{CATALOG}.silver.custbill_records_{NS}"
GOLD_SUMMARY = f"{CATALOG}.gold.finance_billing_summary_{NS}"
GOLD_DELIVERY = f"{CATALOG}.gold.finance_report_delivery_{NS}"
OPS_LEGACY_MIRROR = f"{CATALOG}.ops.legacy_finance_report_{NS}"

# COMMAND ----------

# DDL only on namespace-suffixed tables owned by this unit; never on shared tables.
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {SILVER_TABLE} (
        ns STRING NOT NULL,
        report_date DATE NOT NULL,
        source_file STRING NOT NULL,
        line_no BIGINT NOT NULL,
        cust_id STRING NOT NULL,
        cust_name STRING NOT NULL,
        bill_date STRING NOT NULL,
        amount_cents BIGINT NOT NULL,
        currency STRING NOT NULL,
        record_type STRING NOT NULL
    )"""
)
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {GOLD_SUMMARY} (
        ns STRING NOT NULL,
        report_date DATE NOT NULL,
        currency STRING NOT NULL,
        record_type_name STRING NOT NULL,
        record_count BIGINT NOT NULL,
        total_amount DECIMAL(18,2) NOT NULL
    )"""
)
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {GOLD_DELIVERY} (
        ns STRING NOT NULL,
        report_date DATE NOT NULL,
        run_id STRING NOT NULL,
        artifact_path STRING NOT NULL,
        artifact_sha256 STRING NOT NULL,
        artifact_bytes BIGINT NOT NULL,
        rows_input BIGINT NOT NULL,
        rows_aggregated BIGINT NOT NULL,
        rows_skipped_empty_cust BIGINT NOT NULL,
        rows_attributed_malformed BIGINT NOT NULL,
        delivery_status STRING NOT NULL,
        mail_transport STRING NOT NULL
    )"""
)
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {OPS_LEGACY_MIRROR} (
        ns STRING NOT NULL,
        report_date DATE NOT NULL,
        currency STRING NOT NULL,
        record_type_name STRING NOT NULL,
        record_count BIGINT NOT NULL,
        total_amount DECIMAL(18,2) NOT NULL,
        source_sha256 STRING NOT NULL
    )"""
)

# COMMAND ----------

# Input scan FIRST: an existing-but-unlistable directory must fail the run
# before any destructive slice delete (contract empty_input_semantics). A
# missing directory is created, like the legacy `mkdir -p` before opendir.
os.makedirs(PARSED_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
input_names = sorted(n for n in os.listdir(PARSED_DIR) if is_report_input(n))

batch = ParsedBatch()
input_digests: dict[str, str] = {}
for name in input_names:
    with open(os.path.join(PARSED_DIR, name), "rb") as fh:
        data = fh.read()
    input_digests[name] = sha256_hex(data)
    parse_psv_bytes(data, name, batch)

RUN_ID = deterministic_run_id(NS, REPORT_DATE, input_digests)
print(f"run_id={RUN_ID} inputs={len(input_names)} rows_input={batch.rows_input}")
for item in batch.malformed:
    print(f"attributed malformed row: {item['source_file']}:{item['line_no']} {item['reason']}")

# COMMAND ----------

# Silver: replace only this (ns, report_date) slice — idempotent rerun, no growth.
spark.sql(
    f"DELETE FROM {SILVER_TABLE} WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"
)
if batch.rows:
    silver_df = spark.createDataFrame(
        [
            (NS, REPORT_DATE, r["source_file"], r["line_no"], r["cust_id"], r["cust_name"],
             r["bill_date"], r["amount_cents"], r["currency"], r["record_type"])
            for r in batch.rows
        ],
        "ns STRING, report_date STRING, source_file STRING, line_no BIGINT, cust_id STRING, "
        "cust_name STRING, bill_date STRING, amount_cents BIGINT, currency STRING, record_type STRING",
    )
    silver_df.createOrReplaceTempView("src_finance_silver")
    spark.sql(
        f"""INSERT INTO {SILVER_TABLE}
            SELECT ns, CAST(report_date AS DATE), source_file, line_no, cust_id, cust_name,
                   bill_date, amount_cents, currency, record_type
            FROM src_finance_silver"""
    )

# COMMAND ----------

# Gold summary is computed FROM the silver table (crossfoot by construction),
# never from in-memory state. Empty input ⇒ the slice delete above plus this
# empty aggregation clears the (ns, report_date) summary slice.
spark.sql(
    f"DELETE FROM {GOLD_SUMMARY} WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"
)
spark.sql(
    f"""INSERT INTO {GOLD_SUMMARY}
        SELECT ns, report_date, currency,
               CASE record_type WHEN '01' THEN 'INVOICE' WHEN '02' THEN 'CREDIT'
                    ELSE concat('UNKNOWN(', record_type, ')') END AS record_type_name,
               count(*) AS record_count,
               CAST(sum(amount_cents) / 100.0 AS DECIMAL(18,2)) AS total_amount
        FROM {SILVER_TABLE}
        WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'
        GROUP BY ns, report_date, currency, record_type"""
)

# COMMAND ----------

# Render the artifact from the gold table (the same rows the dashboard reads),
# re-keyed to the legacy "ccy|rt" C-locale sort. Grid cells are exact cents.
gold_rows = spark.sql(
    f"""SELECT currency, record_type_name, record_count,
               CAST(total_amount * 100 AS BIGINT) AS total_cents
        FROM {GOLD_SUMMARY}
        WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"""
).collect()
RT_CODE = {"INVOICE": "01", "CREDIT": "02"}
grid = {}
for row in gold_rows:
    name = row.record_type_name
    if name in RT_CODE:
        rt = RT_CODE[name]
    elif name.startswith("UNKNOWN(") and name.endswith(")"):
        rt = name[len("UNKNOWN("):-1]
    else:
        raise ValueError(f"unrecognized record_type_name in gold: {name!r}")
    grid[(row.currency, rt)] = [row.record_count, row.total_cents]
artifact_bytes = render_report_csv(grid)

# Truthful .csv artifact: the CSV-renamed-.xls defect is not reproduced.
artifact_path = os.path.join(REPORTS_DIR, f"finance_billing_{STAMP}.csv")
with open(artifact_path, "wb") as fh:
    fh.write(artifact_bytes)
with open(artifact_path, "rb") as fh:
    readback = fh.read()
if readback != artifact_bytes:
    raise IOError(f"artifact read-back verification failed for {artifact_path}")
artifact_sha = sha256_hex(readback)
print(f"delivered {artifact_path} ({len(readback)} bytes, sha256={artifact_sha})")

# COMMAND ----------

# Delivery record: verified volume delivery, never a pretended send. The row
# is written only after the read-back digest above succeeded.
spark.sql(
    f"DELETE FROM {GOLD_DELIVERY} WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"
)
delivery_df = spark.createDataFrame(
    [(
        NS, REPORT_DATE, RUN_ID, artifact_path, artifact_sha, len(readback),
        batch.rows_input, len(batch.rows), batch.rows_skipped_empty_cust,
        batch.rows_attributed_malformed, "verified_volume_delivery", "absent",
    )],
    "ns STRING, report_date STRING, run_id STRING, artifact_path STRING, artifact_sha256 STRING, "
    "artifact_bytes BIGINT, rows_input BIGINT, rows_aggregated BIGINT, rows_skipped_empty_cust BIGINT, "
    "rows_attributed_malformed BIGINT, delivery_status STRING, mail_transport STRING",
)
delivery_df.createOrReplaceTempView("src_finance_delivery")
spark.sql(
    f"""INSERT INTO {GOLD_DELIVERY}
        SELECT ns, CAST(report_date AS DATE), run_id, artifact_path, artifact_sha256,
               artifact_bytes, rows_input, rows_aggregated, rows_skipped_empty_cust,
               rows_attributed_malformed, delivery_status, mail_transport
        FROM src_finance_delivery"""
)

# COMMAND ----------

# Legacy report mirror for the demo dashboard: the landed legacy CSV, loaded
# as ow_tp.ops.legacy_finance_report_cnvfinance next to the converted gold rows.
legacy_csv = os.path.join(LEGACY_DIR, f"finance_billing_{STAMP}.csv")
if os.path.isfile(legacy_csv):
    with open(legacy_csv, "rb") as fh:
        legacy_bytes = fh.read()
    legacy_rows = parse_legacy_report_csv(legacy_bytes)
    legacy_sha = sha256_hex(legacy_bytes)
    spark.sql(
        f"DELETE FROM {OPS_LEGACY_MIRROR} WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"
    )
    if legacy_rows:
        mirror_df = spark.createDataFrame(
            [
                (NS, REPORT_DATE, r["currency"], r["record_type_name"],
                 r["record_count"], r["total_amount"], legacy_sha)
                for r in legacy_rows
            ],
            "ns STRING, report_date STRING, currency STRING, record_type_name STRING, "
            "record_count BIGINT, total_amount STRING, source_sha256 STRING",
        )
        mirror_df.createOrReplaceTempView("src_legacy_mirror")
        spark.sql(
            f"""INSERT INTO {OPS_LEGACY_MIRROR}
                SELECT ns, CAST(report_date AS DATE), currency, record_type_name,
                       record_count, CAST(total_amount AS DECIMAL(18,2)), source_sha256
                FROM src_legacy_mirror"""
        )
    print(f"legacy mirror loaded from {legacy_csv} ({len(legacy_rows)} rows, sha256={legacy_sha})")
else:
    print(f"no legacy report landed at {legacy_csv}; mirror left unchanged")

# COMMAND ----------

# Recompute the run's evidence from the platform (never from memory).
for table in (SILVER_TABLE, GOLD_SUMMARY, GOLD_DELIVERY, OPS_LEGACY_MIRROR):
    count = spark.sql(
        f"SELECT COUNT(*) FROM {table} WHERE ns = '{NS}' AND report_date = DATE'{REPORT_DATE}'"
    ).collect()[0][0]
    print(f"{table} rows for ns={NS}, report_date={REPORT_DATE}: {count}")
