from __future__ import annotations

from datetime import datetime

import pytest

from digest import fold_ordered, row_string
from sources import DuckDBSource


def test_spark_all_null_numeric_bounds_match_duckdb() -> None:
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        DecimalType,
        IntegerType,
        StructField,
        StructType,
    )

    from spark_source import _profile

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("dw-harness-null-profile-test")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    duckdb = DuckDBSource(":memory:")
    try:
        duckdb.connection.execute(
            "CREATE TABLE all_nulls (integer_value INTEGER, decimal_value DECIMAL(9, 2))"
        )
        duckdb.connection.execute("INSERT INTO all_nulls VALUES (NULL, NULL)")
        duck_columns = duckdb.columns("main.all_nulls")
        duck_profile = duckdb.profile("main.all_nulls", duck_columns)

        schema = StructType(
            [
                StructField("integer_value", IntegerType(), True),
                StructField("decimal_value", DecimalType(9, 2), True),
            ]
        )
        frame = spark.createDataFrame([(None, None)], schema)
        spark_profile = _profile(frame, list(frame.schema.fields))

        assert tuple(spark_profile[3:6]) == duck_profile[3:6]
        assert tuple(spark_profile[8:11]) == duck_profile[8:11]
    finally:
        duckdb.close()
        spark.stop()


def test_spark_ordered_manifest_splits_composite_key() -> None:
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    from spark_source import build_manifest

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("dw-harness-ordered-manifest-test")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    try:
        schema = StructType(
            [
                StructField("customer_id", LongType(), False),
                StructField("effective_from", TimestampType(), False),
                StructField("customer_sk", LongType(), False),
                StructField("name", StringType(), True),
            ]
        )
        rows = [
            (2, datetime(2024, 2, 1), 20, "second"),
            (1, datetime(2024, 1, 1), 10, "first"),
            (1, datetime(2024, 1, 1), 11, "updated"),
        ]
        frame = spark.createDataFrame(rows, schema=schema)

        class Reader:
            def format(self, _format: str) -> "Reader":
                return self

            def load(self, _path: str):
                return frame

        class Context:
            def addPyFile(self, _path: str) -> None:
                return None

        class SparkAdapter:
            sparkContext = Context()
            read = Reader()

        manifest = build_manifest(
            spark=SparkAdapter(),
            path="unused",
            table="core.dim_customer_scd2",
            fingerprint="test",
            ordered_key="customer_id, effective_from, customer_sk",
        )

        assert manifest.ordered is not None
        ordered_rows = [
            ("1", "2024-01-01 00:00:00", "10", "first"),
            ("1", "2024-01-01 00:00:00", "11", "updated"),
            ("2", "2024-02-01 00:00:00", "20", "second"),
        ]
        expected_digest = fold_ordered(
            row_string(row) for row in ordered_rows
        )[1]
        assert manifest.ordered["digest"] == expected_digest
        permuted_digest = fold_ordered(
            row_string(row) for row in reversed(ordered_rows)
        )[1]
        assert manifest.ordered["digest"] != permuted_digest
    finally:
        spark.stop()
