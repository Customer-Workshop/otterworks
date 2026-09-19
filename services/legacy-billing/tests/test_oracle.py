import sys
from datetime import date
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


class ChangePlanCursor:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.calls.append(("execute", sql, params))

    def callproc(self, name, args):
        self.calls.append(("callproc", name, args))


class ChangePlanConnection:
    def __init__(self):
        self.calls = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return ChangePlanCursor(self.calls)

    def commit(self):
        self.commits += 1


def test_change_plan_closes_same_day_subscription_before_procedure(monkeypatch):
    connection = ChangePlanConnection()
    monkeypatch.setattr(oracle, "oracle_connect", lambda: connection)

    oracle.change_plan("tenant-1", "scale", "2026-09-19")

    assert connection.calls[0][0] == "execute"
    assert "starts_on = :eff" in connection.calls[0][1]
    assert connection.calls[0][2] == {"eff": date(2026, 9, 19), "t": "tenant-1"}
    assert connection.calls[1] == (
        "callproc",
        "pkg_plans.sp_change_plan",
        ["tenant-1", "scale", date(2026, 9, 19)],
    )
    assert connection.commits == 1
