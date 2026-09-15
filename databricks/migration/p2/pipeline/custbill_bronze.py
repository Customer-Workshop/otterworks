"""Bronze layer of the CUSTBILL chain: landed bytes, split into physical records.

Replaces the read half of etl/legacy-extra/jobs/sftp_ingest_poll.ksh. The legacy
poller copies a file to incoming/, copies it again to a timestamped archive, then
deletes it from the drop, swallowing every error on the way. Here the landing
volume is the archive, Auto Loader's own file ledger is the once-only guarantee,
and nothing is ever deleted.

Byte transparency is the whole point of this unit (record contract C-1.3/C-1.4):
the file is read as binary and every record is decoded ISO-8859-1, which maps all
256 byte values to distinct code points and therefore never fails and never
loses a byte. The downstream parser slices *bytes*, so any decode that could
collapse or reject a sequence would silently change the parse.
"""

import os
from fnmatch import fnmatch

from custbill_bytes import split_records
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

LANDING_PATH = spark.conf.get("p2.landing_path")  # noqa: F821 - spark is injected by the pipeline
FILE_GLOB = "CUSTBILL*.dat"

_RECORD = StructType(
    [
        StructField("record_no", LongType(), False),
        StructField("raw_record", StringType(), False),
        StructField("record_bytes", IntegerType(), False),
    ]
)


_LISTED_FILE = StructType(
    [
        StructField("source_file", StringType(), False),
        StructField("landing_path", StringType(), False),
        StructField("file_bytes", LongType(), False),
        StructField("modification_time", LongType(), False),
    ]
)


split_records_udf = F.udf(split_records, ArrayType(_RECORD))


def _list_landing():
    """The landing directory as the filesystem reports it, not as a reader reports it.

    Read through the volume's file path rather than a Spark reader: a Spark file scan
    drops zero-length files before they reach a task, and `LIST` is a command the
    pipeline runtime refuses. The directory listing sees every file that arrived.
    """
    return sorted(
        (
            name,
            f"{LANDING_PATH.rstrip('/')}/{name}",
            os.path.getsize(os.path.join(LANDING_PATH, name)),
            int(os.path.getmtime(os.path.join(LANDING_PATH, name)) * 1000),
        )
        for name in os.listdir(LANDING_PATH)
        if fnmatch(name, FILE_GLOB)
    )


LANDED_FILES = _list_landing()


def _landed_files():
    return (
        spark.readStream.format("cloudFiles")  # noqa: F821
        .option("cloudFiles.format", "binaryFile")
        .option("cloudFiles.includeExistingFiles", "true")
        .option("pathGlobFilter", FILE_GLOB)
        .load(LANDING_PATH)
    )


@dp.table(
    name="custbill_raw",
    comment="One row per physical CUSTBILL record, bytes preserved. Keyed by (source_file, record_no).",
    table_properties={"delta.enableChangeDataFeed": "true"},
    cluster_by=["source_file"],
)
def custbill_raw():
    exploded = _landed_files().select(
        F.element_at(F.split(F.col("path"), "/"), -1).alias("source_file"),
        F.col("modificationTime").alias("file_modified_at"),
        F.explode(split_records_udf(F.col("content"))).alias("rec"),
    )
    return exploded.select(
        "source_file",
        F.col("rec.record_no").alias("record_no"),
        F.col("rec.raw_record").alias("raw_record"),
        F.col("rec.record_bytes").alias("record_bytes"),
        "file_modified_at",
        F.current_timestamp().alias("ingested_at"),
    )


@dp.materialized_view(
    name="custbill_files",
    comment="Processed-file ledger. Replaces the legacy timestamped archive copy; no file is ever deleted.",
)
def custbill_files():
    """Every file in the landing directory, listed from the volume rather than from
    the reader.

    A zero-byte file produces no split and therefore no row from any file reader:
    Spark's file scan drops zero-length files before they reach a task. The legacy
    poller still copied that file and the legacy parser still ran on it (producing
    nothing), so a ledger that could not see it would lose the one fact it exists to
    record - that the file arrived. A directory listing of the volume sees the file
    itself rather than its contents, so an empty file lands here with record_count 0.
    """
    listed = spark.createDataFrame(LANDED_FILES, _LISTED_FILE)  # noqa: F821
    counts = spark.read.table("custbill_raw").groupBy("source_file").count()  # noqa: F821
    return (
        listed.select(
            "source_file",
            "landing_path",
            "file_bytes",
            F.timestamp_millis(F.col("modification_time")).alias("file_modified_at"),
        )
        .join(counts, "source_file", "left")
        .select(
            "source_file",
            "landing_path",
            "file_bytes",
            "file_modified_at",
            F.coalesce(F.col("count"), F.lit(0)).cast("bigint").alias("record_count"),
            F.current_timestamp().alias("ingested_at"),
        )
    )
