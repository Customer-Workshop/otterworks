# Databricks notebook source

"""Converted PySpark implementation of mart.returns_rate_by_category."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def convert(
    spark: SparkSession,
    lakehouse_root: str | Path,
) -> DataFrame:
    root = Path(lakehouse_root)
    items = spark.read.format("delta").load(
        str(root / "core__fct_order_items")
    )
    returns = spark.read.format("delta").load(str(root / "core__fct_returns"))
    sold = items.groupBy("category").agg(
        F.count(F.lit(1)).alias("sold_items")
    )
    returned = returns.groupBy("category").agg(
        F.count(F.lit(1)).alias("returned_items"),
        F.sum("refund_amount").alias("refund_amount"),
    )
    return (
        sold.join(returned, "category", "left")
        .select(
            "category",
            "sold_items",
            F.coalesce("returned_items", F.lit(0)).alias("returned_items"),
            F.coalesce("refund_amount", F.lit(0)).alias("refund_amount"),
        )
        .withColumn(
            "return_rate_pct",
            F.round(
                F.col("returned_items")
                / F.when(F.col("sold_items") != 0, F.col("sold_items")),
                4,
            ).cast("decimal(9,4)"),
        )
    )


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from spark_runtime import local_spark

    spark = local_spark("returns-rate-by-category")
    try:
        root = os.environ.get(
            "DW_LAKEHOUSE_ROOT", "/home/ubuntu/dwdemo/lakehouse"
        )
        output = convert(spark, root)
        output.write.format("delta").mode("overwrite").save(
            str(Path(root) / "mart__returns_rate_by_category")
        )
        output.orderBy("category").show(truncate=False)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
