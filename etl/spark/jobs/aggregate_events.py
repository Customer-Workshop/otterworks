"""
OtterWorks Large-Scale Event Aggregation - PySpark Job

PySpark job for aggregating large volumes of analytics events from S3.
Designed to be triggered by Airflow for heavy processing that exceeds
what the Airflow worker can handle in-memory.

Usage:
    spark-submit --master yarn \
        --deploy-mode cluster \
        aggregate_events.py \
        --input-path s3://otterworks-data-lake/raw-events/ \
        --output-path s3://otterworks-data-lake/aggregated/ \
        --date 2024-01-15
"""

import argparse
import logging
import sys
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("otterworks.aggregate_events")

# Schema for raw analytics events
RAW_EVENT_SCHEMA = StructType(
    [
        StructField("eventType", StringType(), nullable=False),
        StructField("timestamp", StringType(), nullable=False),
        StructField("userId", StringType(), nullable=True),
        StructField("ownerId", StringType(), nullable=True),
        StructField("editedBy", StringType(), nullable=True),
        StructField("authorId", StringType(), nullable=True),
        StructField("deletedBy", StringType(), nullable=True),
        StructField("documentId", StringType(), nullable=True),
        StructField("fileId", StringType(), nullable=True),
        StructField("fileName", StringType(), nullable=True),
        StructField("mimeType", StringType(), nullable=True),
        StructField("sizeBytes", LongType(), nullable=True),
        StructField("title", StringType(), nullable=True),
        StructField("folderId", StringType(), nullable=True),
        StructField("versionNumber", IntegerType(), nullable=True),
        StructField("wordCount", IntegerType(), nullable=True),
        StructField("permission", StringType(), nullable=True),
        StructField("commentId", StringType(), nullable=True),
        StructField("content", StringType(), nullable=True),
    ]
)


def create_spark_session(app_name="OtterWorks-AggregateEvents"):
    """Create and configure a SparkSession."""
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .getOrCreate()
    )


def resolve_user_id(df):
    """Resolve the user ID from whichever field is populated."""
    return df.withColumn(
        "resolved_user_id",
        F.coalesce(
            F.col("userId"),
            F.col("ownerId"),
            F.col("editedBy"),
            F.col("authorId"),
            F.col("deletedBy"),
            F.lit("unknown"),
        ),
    )


def parse_timestamps(df):
    """Parse ISO timestamp strings into proper timestamp columns."""
    return df.withColumn(
        "event_timestamp",
        F.to_timestamp(F.col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
    ).withColumn(
        "event_date",
        F.to_date(F.col("event_timestamp")),
    ).withColumn(
        "event_hour",
        F.hour(F.col("event_timestamp")),
    )


def aggregate_by_user(df):
    """Aggregate events per user per day."""
    return (
        df.groupBy("event_date", "resolved_user_id")
        .agg(
            F.count("*").alias("total_actions"),
            F.countDistinct("eventType").alias("distinct_action_types"),
            F.countDistinct("documentId").alias("documents_touched"),
            F.countDistinct("fileId").alias("files_touched"),
            F.sum(F.when(F.col("eventType") == "document_created", 1).otherwise(0)).alias(
                "documents_created"
            ),
            F.sum(F.when(F.col("eventType") == "document_edited", 1).otherwise(0)).alias(
                "documents_edited"
            ),
            F.sum(F.when(F.col("eventType") == "file_uploaded", 1).otherwise(0)).alias(
                "files_uploaded"
            ),
            F.sum(F.when(F.col("eventType") == "file_shared", 1).otherwise(0)).alias(
                "files_shared"
            ),
            F.sum(F.when(F.col("eventType") == "comment_added", 1).otherwise(0)).alias(
                "comments_added"
            ),
            F.sum(
                F.when(F.col("eventType") == "file_uploaded", F.col("sizeBytes")).otherwise(0)
            ).alias("bytes_uploaded"),
            F.min("event_timestamp").alias("first_action_at"),
            F.max("event_timestamp").alias("last_action_at"),
        )
        .withColumn("active_hours", F.round(
            (F.unix_timestamp("last_action_at") - F.unix_timestamp("first_action_at")) / 3600, 2
        ))
    )


def aggregate_by_document(df):
    """Aggregate events per document per day."""
    doc_events = df.filter(F.col("documentId").isNotNull())
    return doc_events.groupBy("event_date", "documentId").agg(
        F.count("*").alias("total_events"),
        F.countDistinct("resolved_user_id").alias("unique_editors"),
        F.sum(F.when(F.col("eventType") == "document_edited", 1).otherwise(0)).alias("edit_count"),
        F.sum(F.when(F.col("eventType") == "comment_added", 1).otherwise(0)).alias("comment_count"),
        F.max("versionNumber").alias("latest_version"),
        F.max("wordCount").alias("max_word_count"),
    )


def aggregate_by_file(df):
    """Aggregate events per file per day."""
    file_events = df.filter(F.col("fileId").isNotNull())
    return file_events.groupBy("event_date", "fileId").agg(
        F.count("*").alias("total_events"),
        F.first("fileName").alias("file_name"),
        F.first("mimeType").alias("mime_type"),
        F.sum(F.when(F.col("eventType") == "file_shared", 1).otherwise(0)).alias("share_count"),
        F.max("sizeBytes").alias("file_size_bytes"),
    )


def aggregate_hourly(df):
    """Aggregate events by hour for time-series analysis."""
    return df.groupBy("event_date", "event_hour").agg(
        F.count("*").alias("total_events"),
        F.countDistinct("resolved_user_id").alias("active_users"),
        F.countDistinct("documentId").alias("active_documents"),
        F.countDistinct("fileId").alias("active_files"),
    )


def aggregate_daily_summary(df):
    """Compute daily summary statistics."""
    return df.groupBy("event_date").agg(
        F.count("*").alias("total_events"),
        F.countDistinct("resolved_user_id").alias("active_users"),
        F.countDistinct("documentId").alias("active_documents"),
        F.countDistinct("fileId").alias("active_files"),
        F.sum(F.when(F.col("eventType") == "document_created", 1).otherwise(0)).alias(
            "documents_created"
        ),
        F.sum(F.when(F.col("eventType") == "document_edited", 1).otherwise(0)).alias(
            "documents_edited"
        ),
        F.sum(F.when(F.col("eventType") == "comment_added", 1).otherwise(0)).alias(
            "comments_added"
        ),
        F.sum(F.when(F.col("eventType") == "file_uploaded", 1).otherwise(0)).alias(
            "files_uploaded"
        ),
        F.sum(F.when(F.col("eventType") == "file_shared", 1).otherwise(0)).alias(
            "files_shared"
        ),
        F.sum(F.when(F.col("eventType") == "file_deleted", 1).otherwise(0)).alias(
            "files_deleted"
        ),
        F.sum(
            F.when(F.col("eventType") == "file_uploaded", F.col("sizeBytes")).otherwise(0)
        ).alias("bytes_uploaded"),
    )


def run(input_path, output_path, target_date=None):
    """Main aggregation pipeline.

    Args:
        input_path: S3 path to raw event data (JSON or Parquet).
        output_path: S3 path for writing aggregated Parquet output.
        target_date: Optional date filter (YYYY-MM-DD). If None, processes all data.
    """
    spark = create_spark_session()

    logger.info("Reading raw events from %s", input_path)
    raw_df = spark.read.schema(RAW_EVENT_SCHEMA).json(input_path)

    # Apply transformations
    df = resolve_user_id(raw_df)
    df = parse_timestamps(df)

    # Filter to target date if specified
    if target_date:
        logger.info("Filtering to date: %s", target_date)
        df = df.filter(F.col("event_date") == target_date)

    # Cache for multiple aggregations
    df.cache()
    event_count = df.count()
    logger.info("Processing %d events", event_count)

    if event_count == 0:
        logger.warning("No events to process")
        spark.stop()
        return

    # Run aggregations and write partitioned Parquet
    logger.info("Aggregating by user...")
    user_agg = aggregate_by_user(df)
    user_agg.write.partitionBy("event_date").mode("overwrite").parquet(
        f"{output_path}/by_user/"
    )

    logger.info("Aggregating by document...")
    doc_agg = aggregate_by_document(df)
    doc_agg.write.partitionBy("event_date").mode("overwrite").parquet(
        f"{output_path}/by_document/"
    )

    logger.info("Aggregating by file...")
    file_agg = aggregate_by_file(df)
    file_agg.write.partitionBy("event_date").mode("overwrite").parquet(
        f"{output_path}/by_file/"
    )

    logger.info("Aggregating hourly...")
    hourly_agg = aggregate_hourly(df)
    hourly_agg.write.partitionBy("event_date").mode("overwrite").parquet(
        f"{output_path}/hourly/"
    )

    logger.info("Computing daily summary...")
    daily_agg = aggregate_daily_summary(df)
    daily_agg.write.partitionBy("event_date").mode("overwrite").parquet(
        f"{output_path}/daily_summary/"
    )

    df.unpersist()
    logger.info("Aggregation complete. Output written to %s", output_path)

    spark.stop()


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="OtterWorks Event Aggregation Spark Job")
    parser.add_argument(
        "--input-path",
        required=True,
        help="S3 path to raw event data",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="S3 path for aggregated output",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target date to process (YYYY-MM-DD). Omit to process all.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    run(args.input_path, args.output_path, args.date)
