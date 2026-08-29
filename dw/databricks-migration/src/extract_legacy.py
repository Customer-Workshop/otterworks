"""Extract one legacy Postgres table to the configurable Delta landing zone."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import psycopg2
from psycopg2 import sql
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DecimalType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from spark_runtime import local_spark

DEFAULT_DSN = (
    "host=127.0.0.1 port=15432 dbname=analytics_dw "
    "user=dw_admin password=dw_local_dev sslmode=disable"
)
TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def _spark_type(data_type: str, precision: int | None, scale: int | None):
    if data_type in {"bigint"}:
        return LongType()
    if data_type in {"integer", "smallint"}:
        return IntegerType()
    if data_type in {"numeric", "decimal"}:
        return DecimalType(precision or 38, scale or 0)
    if data_type == "boolean":
        return BooleanType()
    if data_type == "date":
        return DateType()
    if data_type.startswith("timestamp"):
        return TimestampType()
    return StringType()


def extract(
    spark: SparkSession,
    table: str,
    dsn: str,
    output_root: Path,
) -> Path:
    schema_name, table_name = table.split(".", 1)
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as metadata:
            metadata.execute(
                """
                SELECT column_name, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema_name, table_name),
            )
            definitions = metadata.fetchall()
        schema = StructType(
            [
                StructField(
                    name,
                    _spark_type(data_type, precision, scale),
                    nullable=True,
                )
                for name, data_type, precision, scale in definitions
            ]
        )
        with connection.cursor(name="legacy_extract") as cursor:
            cursor.itersize = 50_000
            cursor.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                sql.SQL("SELECT * FROM {}").format(
                    sql.Identifier(schema_name, table_name)
                )
            )
            rows = cursor.fetchmany(50_000)
            if not rows:
                frame = spark.createDataFrame([], schema)
            else:
                frame = spark.createDataFrame(rows, schema)
                while True:
                    rows = cursor.fetchmany(50_000)
                    if not rows:
                        break
                    frame = frame.unionByName(spark.createDataFrame(rows, schema))

    destination = output_root / table.replace(".", "__")
    frame.write.format("delta").mode("overwrite").option(
        "overwriteSchema", "true"
    ).save(str(destination))
    print(f"extracted {table} rows={frame.count()} path={destination}")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True)
    parser.add_argument(
        "--dsn", default=os.environ.get("DW_POSTGRES_DSN", DEFAULT_DSN)
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            os.environ.get("DW_LAKEHOUSE_ROOT", "/home/ubuntu/dwdemo/lakehouse")
        ),
    )
    args = parser.parse_args(argv)
    if not TABLE_NAME.fullmatch(args.table):
        parser.error("--table must be schema-qualified")
    spark = local_spark("legacy-postgres-extract")
    try:
        extract(spark, args.table, args.dsn, args.output_root)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
