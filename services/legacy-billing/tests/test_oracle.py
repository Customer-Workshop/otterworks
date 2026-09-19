import sys
from pathlib import Path

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backends import oracle


class DuplicateTenantError(oracledb.IntegrityError):
    pass


class RaceCursor:
    def __init__(self):
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.last_sql = sql
        if "INSERT INTO tenants" in sql:
            raise DuplicateTenantError("ORA-00001: duplicate tenant")

    def fetchone(self):
        return None


class RaceConnection:
    def __init__(self):
        self.rolled_back = False

    def cursor(self):
        return RaceCursor()

    def rollback(self):
        self.rolled_back = True


def test_ensure_tenant_handles_concurrent_tenant_insert():
    connection = RaceConnection()

    assert oracle.ensure_tenant(connection, "tenant-1", "tenant@example.com") is False
    assert connection.rolled_back is True
