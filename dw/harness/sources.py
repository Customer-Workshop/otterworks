"""Database adapters used by the cross-engine manifest builder."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol

import duckdb
import psycopg2

from manifest import Column, normalised_select, profile_select


def _parts(table: str) -> tuple[str, str]:
    schema, separator, relation = table.partition(".")
    if not separator or not schema or not relation:
        raise ValueError(f"table must be schema-qualified: {table!r}")
    return schema, relation


class Source(Protocol):
    def columns(self, table: str) -> list[Column]:
        ...

    def rows(
        self,
        table: str,
        columns: Sequence[Column],
        order_by: str | None = None,
    ) -> Iterator[tuple[str, ...]]:
        ...

    def profile(self, table: str, columns: Sequence[Column]) -> Sequence[Any]:
        ...

    def close(self) -> None:
        ...


class PostgresSource:
    """Postgres adapter with named cursors for bounded row streaming."""

    def __init__(self, dsn: str) -> None:
        self.connection = psycopg2.connect(dsn)

    def columns(self, table: str) -> list[Column]:
        schema, relation = _parts(table)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, relation),
            )
            result = [
                Column(name, type_name, scale)
                for name, type_name, scale in cursor.fetchall()
            ]
        if not result:
            raise ValueError(f"{table}: no columns found")
        return result

    def rows(
        self,
        table: str,
        columns: Sequence[Column],
        order_by: str | None = None,
    ) -> Iterator[tuple[str, ...]]:
        cursor_name = "manifest_rows"
        query = normalised_select(table, columns, order_by=order_by)
        cursor = self.connection.cursor(name=cursor_name)
        cursor.itersize = 50_000
        try:
            cursor.execute(query)
            for row in cursor:
                yield tuple(row)
        finally:
            cursor.close()
            self.connection.rollback()

    def profile(self, table: str, columns: Sequence[Column]) -> Sequence[Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(profile_select(table, columns))
            result = cursor.fetchone()
        self.connection.rollback()
        if result is None:
            raise ValueError(f"{table}: profile query returned no row")
        return result

    def close(self) -> None:
        self.connection.close()


class DuckDBSource:
    """DuckDB adapter with the same manifest-facing interface as Postgres."""

    def __init__(self, database: str) -> None:
        self.connection = duckdb.connect(database)

    def columns(self, table: str) -> list[Column]:
        schema, relation = _parts(table)
        result = self.connection.execute(
            """
            SELECT column_name, data_type, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            (schema, relation),
        ).fetchall()
        columns = [Column(name, type_name, scale) for name, type_name, scale in result]
        if not columns:
            raise ValueError(f"{table}: no columns found")
        return columns

    def rows(
        self,
        table: str,
        columns: Sequence[Column],
        order_by: str | None = None,
    ) -> Iterator[tuple[str, ...]]:
        query = normalised_select(table, columns, order_by=order_by)
        cursor = self.connection.cursor()
        cursor.execute(query)
        while batch := cursor.fetchmany(50_000):
            for row in batch:
                yield tuple(row)

    def profile(self, table: str, columns: Sequence[Column]) -> Sequence[Any]:
        result = self.connection.execute(profile_select(table, columns)).fetchone()
        if result is None:
            raise ValueError(f"{table}: profile query returned no row")
        return result

    def close(self) -> None:
        self.connection.close()
