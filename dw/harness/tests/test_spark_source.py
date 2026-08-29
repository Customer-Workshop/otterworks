from __future__ import annotations

import pytest

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
