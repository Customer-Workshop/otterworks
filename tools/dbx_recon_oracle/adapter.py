"""Oracle source adapter for the dbx-recon harness.

The harness keeps the common SQL adapter logic in the plugin.  This module only
supplies Oracle connection and catalog details, and pins reads with ``AS OF
SCN`` rather than changing the session transaction mode.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any

import oracledb

from recon.adapters import IdentityState, SchemaFacts, Stratum, _SqlAdapterBase, _fk_action, _split_table


_DSN_RE = re.compile(
    r"^(?P<user>[^/@:]+?)/(?P<password>[^@]*)@"
    r"(?P<host>[^/:@]+):(?P<port>[0-9]+)/(?P<service>[^/]+)$"
)
_TABLE_REF_RE = re.compile(
    r"(?P<prefix>\b(?:from|join)\s+)"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_$#]*(?:\.[A-Za-z_][A-Za-z0-9_$#]*)?)",
    re.IGNORECASE,
)


def parse_dsn(value: str) -> tuple[str, str, str]:
    """Return ``(user, password, host:port/service)`` for the fixture DSN form."""
    match = _DSN_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("Oracle DSN must be user/password@host:port/service")
    return match.group("user"), match.group("password"), (
        f"{match.group('host')}:{match.group('port')}/{match.group('service')}"
    )


def connect_oracle(user: str, password: str, dsn: str):
    """Open a thin-mode connection across supported python-oracledb versions."""
    if not oracledb.is_thin_mode():
        oracledb.enable_thin_mode()
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"environment variable {name!r} is empty or unset")
    return value


class OracleSourceAdapter(_SqlAdapterBase):
    """Thin python-oracledb adapter with an Oracle ``AS OF SCN`` window."""

    family = "oracle"
    paramstyle = "named"
    max_params = 1000
    bucket_sql = "NTILE({n}) OVER (ORDER BY {order})"
    datetime_digest_sql = "TRUNC((CAST({col} AS DATE) - DATE '1970-01-01') * 86400000000)"
    binary_literal_sql = "HEXTORAW('{hex}')"

    def __init__(self, dsn_secret: str):
        user, password, dsn = parse_dsn(_secret(dsn_secret))
        super().__init__(connect_oracle(user, password, dsn))
        self._scn: int | None = None

    @classmethod
    def from_connection(cls, connection):
        """Construct an adapter around a fake or already-open connection in tests."""
        obj = cls.__new__(cls)
        _SqlAdapterBase.__init__(obj, connection)
        obj._scn = None
        return obj

    def _table_ref(self, table: str) -> str:
        if self._scn is None:
            return table
        return f"{table} AS OF SCN {self._scn}"

    def _splice_snapshot(self, sql: str) -> str:
        if self._scn is None:
            return sql

        def replace(match: re.Match[str]) -> str:
            table = match.group("table")
            if table.lower() == "dual" or "." not in table:
                return match.group(0)
            tail = sql[match.end():].lstrip().lower()
            if tail.startswith("as of scn"):
                return match.group(0)
            return f"{match.group('prefix')}{table} AS OF SCN {self._scn}"

        return _TABLE_REF_RE.sub(replace, sql)

    def _execute(self, sql: str, params=()):
        return super()._execute(self._splice_snapshot(sql), params)

    def open_window(self) -> str:
        self.window_released = None
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()
        cur = self._execute("SELECT current_scn FROM v$database")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Oracle did not return current_scn")
        self._scn = int(row[0])
        self.isolation = "as_of_scn"
        return self.isolation

    def close_window(self) -> None:
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def discard(self) -> None:
        self.isolation = "none"
        self._conn.close()

    def window_strength(self) -> str:
        return "snapshot" if self._scn is not None else "markers"

    def window_marker(self, table: str, key_cols: list[str], watermark: str | None,
                      where: str | None = None) -> tuple:
        w = f" WHERE {where}" if where else ""
        marks = [f"MAX({watermark})"] if watermark else [f"MAX({k})" for k in key_cols]
        row = self._rows(
            f"SELECT COUNT(*), {', '.join(marks)} FROM {self._table_ref(table)}{w}"
        )[0]
        return tuple(row) + (self._scn,)

    def run_query(self, sql: str) -> list[dict[str, Any]]:
        if not sql.lstrip().lower().startswith(("select", "with")):
            from recon.config import ConfigError
            raise ConfigError("recorded SQL ops must be read-only SELECT or WITH queries")
        cur = self._execute(sql)
        names = [str(d[0]).lower() for d in cur.description or []]
        rows = cur.fetchall()
        self.rows_fetched += len(rows)
        return [dict(zip(names, row)) for row in rows]

    def row_count(self, table: str, where: str | None = None) -> int:
        return super().row_count(self._table_ref(table), where)

    def field_aggregates(self, table: str, column: str, where: str | None = None) -> dict[str, Any]:
        return super().field_aggregates(self._table_ref(table), column, where)

    def sum_probe(self, table: str, column: str, where: str | None = None) -> Any:
        return super().sum_probe(self._table_ref(table), column, where)

    def table_aggregates(self, table: str, columns: list[str], numeric: list[str],
                         where: str | None = None) -> dict[str, dict[str, Any]]:
        return super().table_aggregates(self._table_ref(table), columns, numeric, where)

    def table_aggregates_excluding(self, table: str, columns: list[str], numeric: list[str],
                                   key_cols: list[str], exclude_keys: list[tuple],
                                   where: str | None = None) -> dict[str, dict[str, Any]]:
        return super().table_aggregates_excluding(
            self._table_ref(table), columns, numeric, key_cols, exclude_keys, where
        )

    def fetch_keyed(self, table: str, key_cols: list[str], columns: list[str],
                    where: str | None = None, keys: list[tuple] | None = None
                    ) -> Iterable[dict[str, Any]]:
        return super().fetch_keyed(self._table_ref(table), key_cols, columns, where, keys)

    def iter_keys(self, table: str, key_cols: list[str], where: str | None = None) -> Iterable[tuple]:
        return super().iter_keys(self._table_ref(table), key_cols, where)

    def key_strata(self, table: str, key_cols: list[str], n_strata: int,
                   where: str | None = None) -> list[Stratum]:
        return super().key_strata(self._table_ref(table), key_cols, n_strata, where)

    def sample_keys(self, table: str, key_cols: list[str], lo: Any, hi: Any,
                    row_numbers: list[int], where: str | None = None) -> list[tuple]:
        return super().sample_keys(self._table_ref(table), key_cols, lo, hi, row_numbers, where)

    def duplicate_key_count(self, table: str, key_cols: list[str],
                            where: str | None = None) -> int:
        return super().duplicate_key_count(self._table_ref(table), key_cols, where)

    def range_fingerprints(self, table: str, key_cols: list[str], key_kinds: list[str],
                           watermark: str | None, wm_kind: str | None,
                           ranges: list[tuple[tuple | None, tuple | None]],
                           where: str | None = None) -> list[tuple[int, tuple | None, Any]]:
        return super().range_fingerprints(
            self._table_ref(table), key_cols, key_kinds, watermark, wm_kind, ranges, where
        )

    def keys_in_range(self, table: str, key_cols: list[str], lo: tuple | None, hi: tuple | None,
                      where: str | None = None, extra_cols: list[str] | None = None) -> list[tuple]:
        return super().keys_in_range(self._table_ref(table), key_cols, lo, hi, where, extra_cols)

    def max_watermark(self, table: str, watermark: str, where: str | None = None) -> Any:
        return super().max_watermark(self._table_ref(table), watermark, where)

    def null_key_count(self, table: str, key_cols: list[str], where: str | None = None) -> int:
        return super().null_key_count(self._table_ref(table), key_cols, where)

    def _column_metadata(self, table: str) -> list[tuple]:
        owner, name = _split_table(table, None)
        if owner is None:
            raise ValueError(f"Oracle mapping must qualify table owner: {table}")
        return self._rows(
            "SELECT column_name, data_type, data_scale, nullable "
            "FROM all_tab_columns WHERE owner = :1 AND table_name = :2 "
            "ORDER BY column_id",
            (owner.upper(), name.upper()),
        )

    def numeric_columns(self, table: str) -> set[str]:
        numeric = {
            "NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE",
            "INTEGER", "DECIMAL", "DEC", "SMALLINT",
        }
        return {
            col for col, typ, _scale, _nullable in self._column_metadata(table)
            if str(typ).upper() in numeric
        }

    def whole_number_columns(self, table: str) -> set[str]:
        out = set()
        for col, typ, scale, _nullable in self._column_metadata(table):
            typ = str(typ).upper()
            if typ in {"INTEGER", "SMALLINT"} or (
                typ in {"NUMBER", "DECIMAL", "DEC"} and scale in (None, 0)
            ):
                out.add(col)
        return out

    def schema_facts(self, table: str) -> SchemaFacts:
        owner, name = _split_table(table, None)
        if owner is None:
            raise ValueError(f"Oracle mapping must qualify table owner: {table}")
        owner, name = owner.upper(), name.upper()
        facts = SchemaFacts(table=f"{owner}.{name}")
        rows = self._rows(
            "SELECT c.constraint_type, c.constraint_name, cc.column_name, "
            "       rc.owner, rc.table_name, rcc.column_name, "
            "       c.delete_rule, c.search_condition "
            "FROM all_constraints c "
            "JOIN all_cons_columns cc ON cc.owner = c.owner "
            " AND cc.constraint_name = c.constraint_name AND cc.table_name = c.table_name "
            "LEFT JOIN all_constraints rc ON rc.owner = c.r_owner "
            " AND rc.constraint_name = c.r_constraint_name "
            "LEFT JOIN all_cons_columns rcc ON rcc.owner = rc.owner "
            " AND rcc.constraint_name = rc.constraint_name AND rcc.table_name = rc.table_name "
            " AND rcc.position = cc.position "
            "WHERE c.owner = :1 AND c.table_name = :2 "
            "AND c.constraint_type IN ('P','U','R','C') "
            "ORDER BY c.constraint_name, cc.position",
            (owner, name),
        )
        by_constraint: dict[str, list[Any]] = {}
        for ctype, cname, col, ref_owner, ref_table, ref_col, delete_rule, condition in rows:
            entry = by_constraint.setdefault(
                cname, [ctype, [], None, [], delete_rule, condition]
            )
            if col is not None:
                entry[1].append(str(col).lower())
            if ref_table is not None:
                entry[2] = f"{ref_owner}.{ref_table}".lower()
            if ref_col is not None:
                entry[3].append(str(ref_col).lower())
        for ctype, cols, ref_table, ref_cols, delete_rule, condition in by_constraint.values():
            if ctype == "P":
                facts.primary_key = tuple(cols)
            elif ctype == "U":
                facts.unique.add(tuple(cols))
            elif ctype == "R":
                fk = (tuple(cols), ref_table, tuple(ref_cols))
                facts.foreign_keys.add(fk)
                facts.foreign_key_actions[fk] = ("no action", _fk_action(delete_rule))
            elif ctype == "C":
                facts.check_count += 1
                if condition:
                    facts.checks.add(str(condition))

        for col, _typ, _scale, nullable in self._column_metadata(table):
            if str(nullable).upper() == "N":
                facts.not_null.add(str(col).lower())

        seq_rows = self._rows(
            "SELECT sequence_name FROM all_sequences WHERE sequence_owner = :1",
            (owner,),
        )
        sequences = {str(row[0]).upper() for row in seq_rows}
        if f"SEQ_{name}" in sequences:
            facts.identity_columns.add("log_id" if name == "BILLING_AUDIT_LOG" else "id")
        return facts

    def identity_state(self, table: str, column: str) -> IdentityState | None:
        owner, name = _split_table(table, None)
        if owner is None:
            raise ValueError(f"Oracle mapping must qualify table owner: {table}")
        candidates = [f"SEQ_{name.upper()}"]
        rows = self._rows(
            "SELECT sequence_name, last_number, increment_by "
            "FROM all_sequences WHERE sequence_owner = :1 "
            "AND sequence_name = :2",
            (owner.upper(), candidates[0]),
        )
        if not rows:
            return None
        _sequence, last, increment = rows[0]
        return IdentityState(int(last), int(increment))
