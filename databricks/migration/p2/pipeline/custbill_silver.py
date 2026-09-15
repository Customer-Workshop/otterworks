"""Silver layer: the fixed-width parse, plus the observability the legacy never had.

Replaces etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh. The parse itself is in
`custbill_parse`, which runs against the captured legacy `.psv` files without a
cluster; this module is the Lakeflow wrapper around it.

Three things the legacy did invisibly are now tables:

- `custbill_parsed` carries both the six sliced fields and the rendered `psv_line`.
  Gold re-splits the line, because that is what finance_excel_report.pl reads, and
  aggregating the clean columns instead would silently repair the delimiter bug.
- `custbill_trailer_audit` puts the trailer count next to the parsed count, and counts
  the lines `sed -e '/^HDR/d' -e '/^TRL/d'` removed that look like data records rather
  than headers. The legacy logged the first and never noticed the second (C-4.2/C-4.3).
  ETL-0187 has been open since 2011; this still does not enforce it, it only makes the
  mismatch queryable.

Every expectation warns. None drops. Contract C-6.3 is the acceptance test: gold
holds every record the legacy produced, including the corrupt ones.
"""

import custbill_bytes
import custbill_parse
from custbill_bytes import is_header_or_trailer
from custbill_expectations import (
    FILE_AUDIT_EXPECTATIONS,
    SHADOWED_EXPECTATION,
    SILVER_EXPECTATIONS,
    failed_expectations_sql,
)
from custbill_parse import RECORD_BYTES, parse_record
from pyspark import cloudpickle
from pyspark import pipelines as dp
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

_PARSED = StructType(
    [
        StructField("cust_id", StringType(), False),
        StructField("cust_name", StringType(), False),
        StructField("bill_date_raw", StringType(), False),
        StructField("bill_amt_raw", StringType(), False),
        StructField("currency", StringType(), False),
        StructField("rec_type", StringType(), False),
        StructField("bill_date", StringType(), False),
        StructField("bill_amt", StringType(), False),
        StructField("psv_line", StringType(), False),
        StructField("psv_field_count", IntegerType(), False),
    ]
)

# The pipeline's source directory is on the driver's path, not the Python worker's,
# so a UDF pickled by reference dies on the executor with ModuleNotFoundError. Ship
# the parse itself in the closure instead; it is pure stdlib and a few hundred bytes.
cloudpickle.register_pickle_by_value(custbill_bytes)
cloudpickle.register_pickle_by_value(custbill_parse)

parse_record_udf = F.udf(parse_record, _PARSED)
is_header_or_trailer_udf = F.udf(is_header_or_trailer, "boolean")


def _bronze():
    return spark.readStream.table("custbill_raw")  # noqa: F821 - injected by the pipeline


@dp.table(
    name="ow_tp.silver.custbill",
    comment="One row per parsed CUSTBILL record. Both the sliced fields and the rendered psv_line; nothing is filtered.",
    table_properties={"delta.enableChangeDataFeed": "true"},
    cluster_by=["source_file"],
)
@dp.expect_all(SILVER_EXPECTATIONS)
def custbill_parsed():
    body = _bronze().where(~is_header_or_trailer_udf(F.col("raw_record")))
    return body.withColumn("parsed", parse_record_udf(F.col("raw_record"))).select(
        "source_file",
        "record_no",
        "raw_record",
        "record_bytes",
        "parsed.*",
        F.current_timestamp().alias("parsed_at"),
    )


@dp.materialized_view(
    name="custbill_quarantine",
    comment="Every record that failed an expectation, or that the HDR/TRL rule deleted, with its byte offset and the names of the checks it failed. Observability only - it is never a filter.",
)
def custbill_quarantine():
    """A copy, not a diversion.

    Quarantine exists so a bad record is loud rather than absent. The legacy chain
    processed these rows into the finance report, so removing them here would put
    the target out of parity with the thing it replaces (C-6.1). If this table is
    ever turned into a filter it is a post-cutover decision by the user (P2-D02).

    Two populations, and the difference matters when reading the table:

    - rows that failed an expectation. They are in silver and in gold, unchanged.
    - rows the `sed '/^HDR/d'` prefix rule deleted before parsing. The legacy lost
      them, so the target loses them too and `psv_line` is NULL - they are here to
      be *attributable* (C-6.1), not to be reinstated. Reinstating one would put
      a record in gold that the legacy report never had.
    """
    offsets = _record_byte_offsets()
    failed = (
        spark.read.table("ow_tp.silver.custbill")  # noqa: F821
        .withColumn(
            "failed_expectations",
            F.expr(failed_expectations_sql(SILVER_EXPECTATIONS)),
        )
        .where(F.size("failed_expectations") > 0)
        .select("source_file", "record_no", "raw_record", "record_bytes", "psv_line", "failed_expectations")
    )
    shadowed = _shadowed_data_records().select(
        "source_file",
        "record_no",
        "raw_record",
        "record_bytes",
        F.lit(None).cast("string").alias("psv_line"),
        F.array(F.lit(SHADOWED_EXPECTATION)).alias("failed_expectations"),
    )
    return (
        failed.unionByName(shadowed)
        .join(offsets, ["source_file", "record_no"])
        .select(
            "source_file",
            "record_no",
            "byte_offset",
            "raw_record",
            "record_bytes",
            "psv_line",
            "failed_expectations",
            F.current_timestamp().alias("quarantined_at"),
        )
    )


def _record_byte_offsets():
    """Zero-based offset of each record's first byte in its landed file.

    `record_no` alone does not locate a malformed record in the file, because the
    records are not fixed length in practice - short, long, blank and CR-carrying
    lines all occur. Offsets are derived here rather than carried from bronze so
    the ingest unit's table stays as landed: the split is on LF, so record n starts
    after the bytes of every earlier record plus their one separator byte each.
    """
    preceding = (
        Window.partitionBy("source_file")
        .orderBy("record_no")
        .rowsBetween(Window.unboundedPreceding, -1)
    )
    return (
        spark.read.table("custbill_raw")  # noqa: F821
        .select(
            "source_file",
            "record_no",
            F.coalesce(F.sum(F.col("record_bytes") + F.lit(1)).over(preceding), F.lit(0))
            .cast("bigint")
            .alias("byte_offset"),
        )
    )


def _shadowed_data_records():
    """`sed '/^HDR/d'` is a prefix test, so it also deletes a customer whose id starts HDR.

    There is no way to tell the two apart from the bytes alone, and the legacy did
    not try - it parsed 14 records from a file whose trailer declared 15 and exited
    0. The flag here is a heuristic stated as one: a deleted line that is the full
    65-byte record length and carries eight digits where the bill date belongs is
    almost certainly a shadowed data record, not a header. A real trailer is padded
    with spaces in those columns.
    """
    return (
        spark.read.table("custbill_raw")  # noqa: F821
        .where(is_header_or_trailer_udf(F.col("raw_record")))
        .where(
            (F.col("record_bytes") == F.lit(RECORD_BYTES))
            & F.substring(F.col("raw_record"), 41, 8).rlike("^[0-9]{8}$")
        )
    )


@dp.materialized_view(
    name="custbill_trailer_audit",
    comment="Per file: trailer-declared count vs parsed count vs lines the HDR/TRL deletion shadowed. ETL-0187, logged since 2011 and still not enforced.",
)
@dp.expect_all(FILE_AUDIT_EXPECTATIONS)
def custbill_trailer_audit():
    trailers = (
        spark.read.table("custbill_raw")  # noqa: F821
        .where(F.substring(F.col("raw_record"), 1, 3) == F.lit("TRL"))
        .select(
            "source_file",
            F.substring(F.col("raw_record"), 4, 10).cast("bigint").alias("trailer_count"),
        )
    )
    parsed = (
        spark.read.table("ow_tp.silver.custbill")  # noqa: F821
        .groupBy("source_file")
        .agg(F.count(F.lit(1)).alias("parsed_count"))
    )
    shadowed = _shadowed_data_records().groupBy("source_file").agg(F.count(F.lit(1)).alias("shadowed_count"))
    return (
        spark.read.table("custbill_files")  # noqa: F821
        .select("source_file", "file_bytes", "record_count")
        .join(trailers, "source_file", "left")
        .join(parsed, "source_file", "left")
        .join(shadowed, "source_file", "left")
        .select(
            "source_file",
            "file_bytes",
            F.col("record_count").alias("physical_record_count"),
            "trailer_count",
            F.coalesce(F.col("parsed_count"), F.lit(0)).alias("parsed_count"),
            F.coalesce(F.col("shadowed_count"), F.lit(0)).alias("shadowed_count"),
        )
    )
