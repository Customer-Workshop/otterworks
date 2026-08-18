# Databricks notebook source
# MAGIC %md
# MAGIC # ow_tp_ingest_cnvingest — CUSTBILL drop ingest (converted from sftp_ingest_poll.ksh)
# MAGIC
# MAGIC Transport-only, byte-transparent, per-batch (manual trigger, `max_concurrent_runs=1`).
# MAGIC Contract: `docs/tech-partnerships/contracts/sftp_ingest_poll-cnvingest.contract.json`.
# MAGIC All paths and table names derive from the `ns` job parameter — no hostname
# MAGIC branching, no lock files.

# COMMAND ----------

import os
import sys

dbutils.widgets.text("ns", "cnvingest")
NS = dbutils.widgets.get("ns")

notebook_dir = os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
)
sys.path.append(f"/Workspace{notebook_dir}")
from ingest_core import StagedFile, ingest_batch, require_ns  # noqa: E402

require_ns(NS)
CATALOG = "ow_tp"
ROOT = f"/Volumes/{CATALOG}/bronze/landing/{NS}/sftp_ingest_poll"
FILES_TABLE = f"{CATALOG}.bronze.custbill_ingest_files_{NS}"
RAW_TABLE = f"{CATALOG}.bronze.custbill_raw_{NS}"

# COMMAND ----------

# DDL only on namespace-suffixed tables owned by this unit; never on shared tables.
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {FILES_TABLE} (
        ns STRING NOT NULL,
        file_name STRING NOT NULL,
        sha256 STRING NOT NULL,
        bytes BIGINT NOT NULL,
        lines BIGINT NOT NULL,
        ingest_id STRING NOT NULL
    )"""
)
spark.sql(
    f"""CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
        ns STRING NOT NULL,
        file_name STRING NOT NULL,
        sha256 STRING NOT NULL,
        line_no BIGINT NOT NULL,
        line STRING NOT NULL
    )"""
)

# COMMAND ----------


class DeltaBronze:
    """MERGE-based registration keyed on (ns, file_name, sha256[, line_no]).

    Idempotent: re-registering a byte-identical file matches every key and
    duplicates nothing.
    """

    def __init__(self, spark, ns: str):
        self.spark = spark
        self.ns = ns

    def register(self, staged: StagedFile, raw_lines: list[str]) -> None:
        files_df = self.spark.createDataFrame(
            [(self.ns, staged.file_name, staged.sha256, staged.bytes, staged.lines, staged.ingest_id)],
            "ns STRING, file_name STRING, sha256 STRING, bytes BIGINT, lines BIGINT, ingest_id STRING",
        )
        files_df.createOrReplaceTempView("src_ingest_file")
        self.spark.sql(
            f"""MERGE INTO {FILES_TABLE} t USING src_ingest_file s
                ON t.ns = s.ns AND t.file_name = s.file_name AND t.sha256 = s.sha256
                WHEN NOT MATCHED THEN INSERT *"""
        )
        raw_df = self.spark.createDataFrame(
            [
                (self.ns, staged.file_name, staged.sha256, i + 1, line)
                for i, line in enumerate(raw_lines)
            ],
            "ns STRING, file_name STRING, sha256 STRING, line_no BIGINT, line STRING",
        )
        raw_df.createOrReplaceTempView("src_ingest_raw")
        self.spark.sql(
            f"""MERGE INTO {RAW_TABLE} t USING src_ingest_raw s
                ON t.ns = s.ns AND t.file_name = s.file_name
                   AND t.sha256 = s.sha256 AND t.line_no = s.line_no
                WHEN NOT MATCHED THEN INSERT *"""
        )


# COMMAND ----------

staged = ingest_batch(ROOT, NS, DeltaBronze(spark, NS))
if staged:
    for rec in staged:
        print(f"ingested {rec.file_name} ({rec.bytes} bytes, {rec.lines} raw lines, sha256={rec.sha256})")
else:
    print("empty drop: no-op")

# COMMAND ----------

# Recompute counts from the platform (never from memory) for the run log.
for table in (FILES_TABLE, RAW_TABLE):
    count = spark.sql(f"SELECT COUNT(*) FROM {table} WHERE ns = '{NS}'").collect()[0][0]
    print(f"{table} rows for ns={NS}: {count}")
