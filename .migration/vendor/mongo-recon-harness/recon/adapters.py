"""Source and target adapters.

Tiers 1-3 talk only to these interfaces, so a fake adapter (tests) and a partner MCP
delegation (future) plug in without touching tier logic. Aggregates are computed natively
on each side (SQL on source, aggregation pipeline on target) so no bulk data crosses the
wire. Drivers are imported lazily; installing only the extras you need is supported.

Connection secrets are read from environment variables BY NAME; the harness never accepts
a literal connection string on the CLI.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Protocol


class SourceAdapter(Protocol):
    def row_count(self, table: str, where: str | None = None) -> int: ...
    def field_aggregates(self, table: str, column: str, where: str | None = None) -> dict[str, Any]: ...
    def fetch_keyed(self, table: str, key_cols: list[str], columns: list[str],
                    where: str | None = None, keys: list[tuple] | None = None) -> Iterable[dict[str, Any]]: ...
    def key_strata(self, table: str, key_cols: list[str], n_strata: int) -> list[tuple]: ...


class TargetAdapter(Protocol):
    def doc_count(self, collection: str) -> int: ...
    def embedded_count(self, collection: str, array_path: str) -> int: ...
    def field_aggregates(self, collection: str, field_path: str) -> dict[str, Any]: ...
    def fetch_keyed(self, collection: str, key_field: str, fields: list[str],
                    keys: list[Any] | None = None) -> Iterable[dict[str, Any]]: ...


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"secret '{name}' not found in environment; pass secrets by name only")
    return value


AGG_SQL = ("SELECT COUNT(*) AS n, COUNT({col}) AS nonnull, MIN({col}) AS mn, "
           "MAX({col}) AS mx, COUNT(DISTINCT {col}) AS dc FROM {table}{where}")


class _SqlAdapterBase:
    """Shared SQL-side implementation; subclasses provide a DB-API connection."""

    def __init__(self, conn):
        self._conn = conn

    def _rows(self, sql: str, params: tuple = ()) -> list[tuple]:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def row_count(self, table: str, where: str | None = None) -> int:
        w = f" WHERE {where}" if where else ""
        return int(self._rows(f"SELECT COUNT(*) FROM {table}{w}")[0][0])

    def field_aggregates(self, table: str, column: str, where: str | None = None) -> dict[str, Any]:
        w = f" WHERE {where}" if where else ""
        n, nonnull, mn, mx, dc = self._rows(AGG_SQL.format(col=column, table=table, where=w))[0]
        out = {"count": int(n), "null_rate": (int(n) - int(nonnull)) / int(n) if n else 0.0,
               "min": mn, "max": mx, "distinct_count": int(dc)}
        try:
            (s,) = self._rows(f"SELECT SUM({column}) FROM {table}{w}")[0]
            out["sum"] = s
        except Exception:
            out["sum"] = None  # non-numeric column
        return out

    def fetch_keyed(self, table: str, key_cols: list[str], columns: list[str],
                    where: str | None = None, keys: list[tuple] | None = None) -> Iterable[dict[str, Any]]:
        cols = ", ".join(dict.fromkeys(key_cols + columns))
        w = f" WHERE {where}" if where else ""
        cur = self._conn.cursor()
        cur.execute(f"SELECT {cols} FROM {table}{w} ORDER BY {', '.join(key_cols)}")
        names = [d[0] for d in cur.description]
        wanted = {tuple(k) for k in keys} if keys is not None else None
        for row in cur:
            rec = dict(zip(names, row))
            if wanted is None or tuple(rec[k] for k in key_cols) in wanted:
                yield rec

    def key_strata(self, table: str, key_cols: list[str], n_strata: int) -> list[tuple]:
        key = key_cols[0]
        rows = self._rows(f"SELECT MIN({key}), MAX({key}) FROM {table}")
        return [rows[0]] if rows else []


class OracleSourceAdapter(_SqlAdapterBase):
    def __init__(self, dsn_secret: str):
        import oracledb  # lazy: optional extra
        user, password, dsn = _secret(dsn_secret).split("/", 2)
        super().__init__(oracledb.connect(user=user, password=password, dsn=dsn))


class SqlServerSourceAdapter(_SqlAdapterBase):
    def __init__(self, dsn_secret: str):
        import pyodbc  # lazy: optional extra
        super().__init__(pyodbc.connect(_secret(dsn_secret)))


class MongoTargetAdapter:
    def __init__(self, uri_secret: str, database: str):
        from pymongo import MongoClient  # lazy: optional extra
        self._db = MongoClient(_secret(uri_secret))[database]

    def doc_count(self, collection: str) -> int:
        return self._db[collection].count_documents({})

    def embedded_count(self, collection: str, array_path: str) -> int:
        out = list(self._db[collection].aggregate([
            {"$project": {"n": {"$size": {"$ifNull": [f"${array_path}", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$n"}}},
        ]))
        return int(out[0]["total"]) if out else 0

    def field_aggregates(self, collection: str, field_path: str) -> dict[str, Any]:
        f = f"${field_path}"
        out = list(self._db[collection].aggregate([
            {"$group": {"_id": None, "count": {"$sum": 1},
                        "nonnull": {"$sum": {"$cond": [{"$in": [{"$type": f}, ["missing", "null"]]}, 0, 1]}},
                        "mn": {"$min": f}, "mx": {"$max": f}, "sm": {"$sum": f}}},
        ]))
        dc = list(self._db[collection].aggregate([
            {"$group": {"_id": f}}, {"$count": "n"}]))
        if not out:
            return {"count": 0, "null_rate": 0.0, "min": None, "max": None, "sum": None, "distinct_count": 0}
        g = out[0]
        n = int(g["count"])
        return {"count": n, "null_rate": (n - int(g["nonnull"])) / n if n else 0.0,
                "min": g["mn"], "max": g["mx"], "sum": g["sm"],
                "distinct_count": int(dc[0]["n"]) if dc else 0}

    def fetch_keyed(self, collection: str, key_field: str, fields: list[str],
                    keys: list[Any] | None = None) -> Iterable[dict[str, Any]]:
        query = {key_field: {"$in": keys}} if keys is not None else {}
        proj = {f: 1 for f in fields} | {key_field: 1}
        yield from self._db[collection].find(query, proj).sort(key_field, 1)


class MongoSourceAdapter:
    """Self-hosted Mongo as the SOURCE (mongodb-atlas family). Wraps a target-style
    adapter behind the SourceAdapter interface; 'table' means source collection."""

    def __init__(self, uri_secret: str, database: str):
        self._t = MongoTargetAdapter(uri_secret, database)

    def row_count(self, table: str, where: str | None = None) -> int:
        return self._t.doc_count(table)

    def field_aggregates(self, table: str, column: str, where: str | None = None) -> dict[str, Any]:
        return self._t.field_aggregates(table, column)

    def fetch_keyed(self, table, key_cols, columns, where=None, keys=None):
        for doc in self._t.fetch_keyed(table, key_cols[0], columns,
                                       [k[0] for k in keys] if keys else None):
            yield doc

    def key_strata(self, table: str, key_cols: list[str], n_strata: int) -> list[tuple]:
        return []
