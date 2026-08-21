"""Fixtures for the parity suite.

The parity tests need the real fixture database — they exist to prove the
extracted rules leave the same rows behind as the PL/SQL did. When it is not
reachable they skip rather than fail, so the rule tests still run anywhere.

Whatever the parity tests write is undone at the end of the session: the tables
are snapshotted before the first test and restored after the last one, so the
Oracle suites can be run before or after ``make insurance-parity`` and see the
state they expect.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import oracledb
import pytest

from app.db import connect
from app.repository import decimal_output_handler

# Child-before-parent, so restoring in reverse order never trips a foreign key.
SNAPSHOT_TABLES = (
    "rate_audit_log",
    "commission_ledger",
    "commission_splits",
    "commission_rates",
    "policies",
    "agents",
    "products",
)


@pytest.fixture(scope="session")
def connection() -> Iterator[oracledb.Connection]:
    try:
        oracle = connect()
    except (oracledb.Error, OSError) as error:
        pytest.skip(f"insurance fixture not reachable ({error}); run: make insurance-up NS=<ns>")
    try:
        yield oracle
    finally:
        oracle.close()


@pytest.fixture(scope="session", autouse=True)
def _restore_database() -> Iterator[None]:
    try:
        oracle = connect()
    except (oracledb.Error, OSError):
        yield  # no fixture database: the parity tests skip, nothing to restore
        return
    snapshot = {table: _dump(oracle, table) for table in SNAPSHOT_TABLES}
    try:
        yield
    finally:
        _restore(oracle, snapshot)
        oracle.close()


def _dump(oracle: oracledb.Connection, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    with oracle.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {table}")  # noqa: S608 - fixed table names
        columns = [column.name for column in cursor.description]
        return columns, cursor.fetchall()


def _restore(
    oracle: oracledb.Connection, snapshot: dict[str, tuple[list[str], list[tuple[Any, ...]]]]
) -> None:
    with oracle.cursor() as cursor:
        for table in SNAPSHOT_TABLES:
            cursor.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
        for table in reversed(SNAPSHOT_TABLES):
            columns, rows = snapshot[table]
            if not rows:
                continue
            placeholders = ", ".join(f":{index}" for index in range(1, len(columns) + 1))
            cursor.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                rows,
            )
    oracle.commit()


@pytest.fixture
def query(connection: oracledb.Connection):
    """Read committed state back, the way the Oracle suite inspects its results."""

    def run(sql: str, **binds: Any) -> list[tuple[Any, ...]]:
        connection.commit()  # end the read-only transaction so the next read is fresh
        with connection.cursor() as cursor:
            # Read NUMBER as Decimal, so amounts are compared exactly.
            cursor.outputtypehandler = decimal_output_handler
            cursor.execute(sql, binds)
            return cursor.fetchall()

    return run
