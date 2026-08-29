"""Build the manifest that describes one table's contents.

A manifest is the unit of evidence in this demo: for a given table it records
the row count, an order-independent row digest, and per-column digests plus a
small profile (non-null count, distinct count, min, max, and sum for numerics).
Everything a gate compares comes from a manifest, so the same code path produces
the legacy Redshift-stand-in evidence, the DuckDB rebuild evidence, and the
converted Spark/Delta evidence.

The normalisation of a value to text happens in the engine (see
``normalised_select``), and is deliberately identical everywhere:
fixed-scale decimal text, second-resolution timestamps, ``true``/``false``, and
``\\N`` for NULL. See ``digest.py`` for why the hashing itself is done in Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from digest import NULL_SENTINEL, column_digests, fold_ordered, row_string

MANIFEST_FORMAT = 4
NUMERIC_TYPES = {"numeric", "decimal", "integer", "bigint", "int", "smallint",
                 "int4", "int8", "int2", "double", "float", "real"}


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str
    scale: int | None = None

    @property
    def is_numeric(self) -> bool:
        return self.type_name.lower().split("(")[0] in NUMERIC_TYPES


@dataclass
class Manifest:
    table: str
    engine: str
    row_count: int
    row_digest: int
    columns: list[dict] = field(default_factory=list)
    ordered: dict | None = None
    fingerprint: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "manifest_format": MANIFEST_FORMAT,
                "table": self.table,
                "engine": self.engine,
                "row_count": self.row_count,
                "row_digest": self.row_digest,
                "columns": self.columns,
                "ordered": self.ordered,
                "fingerprint": self.fingerprint,
            },
            indent=2,
            sort_keys=True,
        )

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n")
        return path

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        raw = json.loads(Path(path).read_text())
        if raw.get("manifest_format") != MANIFEST_FORMAT:
            raise ValueError(
                f"{path}: manifest_format {raw.get('manifest_format')!r}, "
                f"this harness writes {MANIFEST_FORMAT} -- re-record instead of "
                "comparing across formats"
            )
        return cls(
            table=raw["table"],
            engine=raw["engine"],
            row_count=raw["row_count"],
            row_digest=raw["row_digest"],
            columns=raw["columns"],
            ordered=raw.get("ordered"),
            fingerprint=raw.get("fingerprint"),
        )


def normalise(column: Column) -> str:
    """SQL expression normalising one column to canonical text.

    Timestamps are truncated to seconds *and* rendered without a timezone
    suffix; the legacy estate stores naive local timestamps and the converted
    assets must land the same instant, so any timezone handling difference has
    to show up as a digest mismatch rather than being papered over here.
    """
    name = f'"{column.name}"'
    base = column.type_name.lower().split("(")[0]
    if base in {"timestamp", "timestamptz", "timestamp without time zone",
                "timestamp with time zone"}:
        expr = f"CAST(DATE_TRUNC('second', {name}) AS VARCHAR)"
    elif base == "date":
        expr = f"CAST({name} AS VARCHAR)"
    elif base in {"boolean", "bool"}:
        # The NULL arm is explicit so COALESCE below still sees a NULL: mapping
        # an unknown flag to 'false' would make the digest blind to the
        # difference between "no" and "not recorded".
        expr = (
            f"CASE WHEN {name} IS NULL THEN NULL "
            f"WHEN {name} THEN 'true' ELSE 'false' END"
        )
    elif base in {"numeric", "decimal"} and column.scale is not None:
        expr = f"CAST(ROUND({name}, {column.scale}) AS VARCHAR)"
    else:
        expr = f"CAST({name} AS VARCHAR)"
    return f"COALESCE({expr}, '{NULL_SENTINEL}')"


def normalised_select(table: str, columns: Sequence[Column],
                      where: str | None = None,
                      order_by: str | None = None) -> str:
    projection = ",\n       ".join(normalise(c) for c in columns)
    sql = f"SELECT {projection}\nFROM {table}"
    if where:
        sql += f"\nWHERE {where}"
    if order_by:
        sql += f"\nORDER BY {order_by}"
    return sql


def bound(column: Column, function: str) -> str:
    """Normalised MIN/MAX expression.

    Numeric bounds are taken on the *native* column and normalised afterwards;
    taking them on the text projection would order lexicographically, so a
    profile would report 100 as smaller than 9 and quietly disagree with itself
    across engines.
    """
    name = f'"{column.name}"'
    if column.is_numeric:
        aggregate = f"{function}({name})"
        if column.scale is not None:
            aggregate = f"ROUND({aggregate}, {column.scale})"
        return f"COALESCE(CAST({aggregate} AS VARCHAR), '{NULL_SENTINEL}')"
    return f"{function}({normalise(column)})"


def profile_select(table: str, columns: Sequence[Column],
                   where: str | None = None) -> str:
    """Portable per-column profile: non-null, distinct, min, max, numeric sum."""
    parts: list[str] = ["COUNT(*)"]
    for column in columns:
        name = f'"{column.name}"'
        norm = normalise(column)
        parts.append(f"COUNT({name})")
        parts.append(f"COUNT(DISTINCT {norm})")
        parts.append(bound(column, "MIN"))
        parts.append(bound(column, "MAX"))
        parts.append(
            f"CAST(SUM({name}) AS VARCHAR)" if column.is_numeric else "NULL"
        )
    sql = f"SELECT {', '.join(parts)}\nFROM {table}"
    if where:
        sql += f"\nWHERE {where}"
    return sql


def build(
    table: str,
    engine: str,
    columns: Sequence[Column],
    rows: Iterable[Sequence[str]],
    profile_row: Sequence,
    ordered_rows: Iterator[Sequence[str]] | None = None,
    ordered_key: str | None = None,
    fingerprint: str | None = None,
) -> Manifest:
    row_count, row_digest, digests = column_digests(
        (tuple(r) for r in rows), len(columns)
    )

    profile: list[dict] = []
    total_rows = int(profile_row[0])
    for idx, column in enumerate(columns):
        offset = 1 + idx * 5
        profile.append(
            {
                "name": column.name,
                "type": column.type_name,
                "scale": column.scale,
                "digest": digests[idx],
                "non_null": int(profile_row[offset]),
                "distinct": int(profile_row[offset + 1]),
                "min": profile_row[offset + 2],
                "max": profile_row[offset + 3],
                "sum": profile_row[offset + 4],
            }
        )

    if total_rows != row_count:
        raise ValueError(
            f"{table}: profile counted {total_rows} rows but the digest pass "
            f"counted {row_count} -- the table changed underneath the harness"
        )

    ordered = None
    if ordered_rows is not None:
        if not ordered_key:
            raise ValueError("ordered_rows requires ordered_key")
        count, digest = fold_ordered(row_string(tuple(r)) for r in ordered_rows)
        if count != row_count:
            raise ValueError(
                f"{table}: ordered pass saw {count} rows, unordered pass saw "
                f"{row_count}"
            )
        ordered = {"key": ordered_key, "digest": digest}

    return Manifest(
        table=table,
        engine=engine,
        row_count=row_count,
        row_digest=row_digest,
        columns=profile,
        ordered=ordered,
        fingerprint=fingerprint,
    )
