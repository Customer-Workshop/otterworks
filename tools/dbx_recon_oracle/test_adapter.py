from __future__ import annotations

import pytest

from .adapter import OracleSourceAdapter, parse_dsn


class FakeCursor:
    def __init__(self, rows=(), description=()):
        self.rows = list(rows)
        self.description = list(description)
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, cursors):
        self.cursors = iter(cursors)
        self.statements = []
        self.rollbacks = 0

    def cursor(self):
        cursor = next(self.cursors)
        self.statements.append(cursor)
        return cursor

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def adapter_with(*cursors):
    return OracleSourceAdapter.from_connection(FakeConnection(cursors))


def test_parse_dsn():
    assert parse_dsn("ow_billing/secret@localhost:52521/FREEPDB1") == (
        "ow_billing",
        "secret",
        "localhost:52521/FREEPDB1",
    )


def test_parse_dsn_rejects_other_shapes():
    with pytest.raises(ValueError):
        parse_dsn("postgresql://localhost/db")


def test_open_window_pins_scn_once_and_splices_table_reference():
    scn = FakeCursor(rows=[(12345,)])
    marker = FakeCursor(rows=[(3, 123)])
    adapter = adapter_with(scn, marker)
    assert adapter.open_window() == "as_of_scn"
    assert adapter.window_marker("OW_BILLING.CODES", ["CODE_VAL"], None) == (3, 123, 12345)
    assert adapter.statements == 2
    sql, _params = adapter._conn.statements[-1].executed[0]
    assert "OW_BILLING.CODES AS OF SCN 12345" in sql


def test_run_query_lowercases_oracle_column_names():
    cursor = FakeCursor(rows=[("abc", 2)], description=[("CODE_TYPE",), ("CODE_VAL",)])
    adapter = adapter_with(cursor)
    assert adapter.run_query("SELECT CODE_TYPE, CODE_VAL FROM OW_BILLING.CODES") == [
        {"code_type": "abc", "code_val": 2}
    ]


def test_every_execute_counts_as_one_statement():
    first = FakeCursor(rows=[(123,)])
    second = FakeCursor(rows=[(1,)])
    adapter = adapter_with(first, second)
    adapter.open_window()
    adapter.row_count("OW_BILLING.CODES")
    assert adapter.statements == 2
