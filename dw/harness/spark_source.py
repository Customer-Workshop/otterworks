"""Build Python-digest manifests from Spark/Delta tables."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    ByteType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    ShortType,
    TimestampType,
)

from digest import combine_unordered, column_digests, fold_ordered, row_string
from manifest import Column, Manifest

NULL_SENTINEL = "\\N"


def _normalised_column(field: Any):
    """Return a Spark expression with the manifest's canonical text rules."""
    column = F.col(field.name)
    data_type = field.dataType
    if isinstance(data_type, TimestampType):
        expression = F.date_format(column, "yyyy-MM-dd HH:mm:ss")
    elif isinstance(data_type, DateType):
        expression = F.date_format(column, "yyyy-MM-dd")
    elif isinstance(data_type, BooleanType):
        expression = F.when(column.isNull(), F.lit(None).cast("string")).when(
            column, F.lit("true")
        ).otherwise(F.lit("false"))
    elif isinstance(data_type, DecimalType):
        formatted = F.format_number(
            column.cast(DecimalType(38, data_type.scale)), data_type.scale
        )
        expression = F.regexp_replace(formatted, ",", "")
    else:
        expression = column.cast("string")
    return F.coalesce(expression, F.lit(NULL_SENTINEL))


def _decimal_text(expression: Any, scale: int):
    return F.regexp_replace(
        F.format_number(
            expression.cast(DecimalType(38, scale)),
            scale,
        ),
        ",",
        "",
    )


def _is_numeric(data_type: Any) -> bool:
    return isinstance(
        data_type,
        (
            ByteType,
            ShortType,
            IntegerType,
            LongType,
            FloatType,
            DoubleType,
            DecimalType,
        ),
    )


def _fold_partition(
    rows: Iterable[Any], column_count: int
) -> Iterable[tuple[int, int, list[int]]]:
    values = (tuple(row) for row in rows)
    count, row_digest, digests = column_digests(values, column_count)
    yield count, row_digest, digests


def _profile(frame: DataFrame, fields: list[Any]) -> list[Any]:
    expressions: list[Any] = [F.count(F.lit(1))]
    for field in fields:
        column = F.col(field.name)
        normalised = _normalised_column(field)
        expressions.extend(
            [
                F.count(column),
                F.countDistinct(normalised),
            ]
        )
        if isinstance(field.dataType, DecimalType):
            expressions.extend(
                [
                    _decimal_text(F.min(column), field.dataType.scale),
                    _decimal_text(F.max(column), field.dataType.scale),
                    _decimal_text(F.sum(column), field.dataType.scale),
                ]
            )
        elif _is_numeric(field.dataType):
            expressions.extend(
                [
                    F.min(column).cast("string"),
                    F.max(column).cast("string"),
                    F.sum(column).cast("string"),
                ]
            )
        else:
            expressions.extend([F.min(normalised), F.max(normalised), F.lit(None).cast("string")])
    return list(frame.agg(*expressions).collect()[0])


def build_manifest(
    spark: SparkSession,
    path: str,
    table: str,
    fingerprint: str,
    ordered_key: str | None = None,
) -> Manifest:
    """Read a Delta path and build a manifest using Python digest code."""
    harness_dir = Path(__file__).resolve().parent
    for module in ("digest.py", "manifest.py", "spark_source.py"):
        spark.sparkContext.addPyFile(str(harness_dir / module))
    frame = spark.read.format("delta").load(path)
    fields = list(frame.schema.fields)
    columns = [
        Column(field.name, field.dataType.simpleString(), getattr(field.dataType, "scale", None))
        for field in fields
    ]
    projected = frame.select(*[_normalised_column(field) for field in fields])
    partitions = projected.rdd.mapPartitions(
        partial(_fold_partition, column_count=len(fields))
    ).collect()
    row_count, row_digest = combine_unordered(
        (part_count, part_digest)
        for part_count, part_digest, _ in partitions
    )
    column_digests_result = [
        combine_unordered(
            (part_count, part_digests[index])
            for part_count, _, part_digests in partitions
        )[1]
        for index in range(len(fields))
    ]

    profile_row = _profile(frame, fields)
    profile: list[dict[str, Any]] = []
    for index, column in enumerate(columns):
        offset = 1 + index * 5
        profile.append(
            {
                "name": column.name,
                "type": column.type_name,
                "digest": column_digests_result[index],
                "non_null": int(profile_row[offset]),
                "distinct": int(profile_row[offset + 1]),
                "min": profile_row[offset + 2],
                "max": profile_row[offset + 3],
                "sum": profile_row[offset + 4],
            }
        )

    ordered = None
    if ordered_key:
        ordered_frame = frame.orderBy(F.expr(ordered_key)).select(
            *[_normalised_column(field) for field in fields]
        )
        count, digest = fold_ordered(
            row_string(tuple(row)) for row in ordered_frame.toLocalIterator()
        )
        if count != row_count:
            raise ValueError(
                f"{table}: ordered pass saw {count} rows, unordered pass saw {row_count}"
            )
        ordered = {"key": ordered_key, "digest": digest}

    return Manifest(
        table=table,
        engine="spark-delta",
        row_count=row_count,
        row_digest=row_digest,
        columns=profile,
        ordered=ordered,
        fingerprint=fingerprint,
    )
