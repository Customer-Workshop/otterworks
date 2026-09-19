import sys
from pathlib import Path

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import backends
import facade as facade_module
from app import app


def test_facade_requires_identity(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().get("/api/v1/billing/me")
    assert response.status_code == 401


def test_admin_facade_requires_role(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().get(
        "/api/v1/billing/admin/overdue",
        headers={"X-User-ID": "tenant"},
    )
    assert response.status_code == 403


def test_facade_is_unavailable_in_postgres_mode(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "postgres")
    response = app.test_client().get("/api/v1/billing/plans")
    assert response.status_code == 501
    assert response.get_json() == {"error": "not available on this backend"}


def test_facade_plans_shape(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(
        facade_module.oracle,
        "list_plans",
        lambda: [
            {
                "plan_id": "p1",
                "code": "GROWTH",
                "tier": "growth",
                "monthly_fee": "149.00",
                "included_units": 500,
                "overage_rate": "0.035000",
            }
        ],
    )
    response = app.test_client().get("/api/v1/billing/plans")
    assert response.status_code == 200
    assert response.get_json() == [
        {
            "plan_id": "p1",
            "plan_code": "GROWTH",
            "tier": "growth",
            "monthly_fee": "149.00",
            "included_units": 500,
            "overage_rate": "0.035000",
        }
    ]


def test_me_shape(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(facade_module, "_ensure", lambda tenant_id: None)
    monkeypatch.setattr(
        facade_module.oracle,
        "entitlement",
        lambda tenant_id, on: [{"tenant_id": tenant_id, "plan_code": "GROWTH"}],
    )
    rows = iter(
        [
            [{"tenant_id": "t1", "name": "admin@example.com", "status": "active", "tax_exempt": "N"}],
            [{"cust_no": "OW-1", "cust_name": "Admin", "cur_bal_amt": "1.00"}],
        ]
    )
    monkeypatch.setattr(facade_module.oracle, "query", lambda sql, params=(): next(rows))
    response = app.test_client().get(
        "/api/v1/billing/me",
        headers={"X-User-ID": "t1", "X-User-Email": "admin@example.com"},
    )
    assert response.status_code == 200
    assert response.get_json()["entitlement"][0]["plan_code"] == "GROWTH"
    assert response.get_json()["customer"]["cust_no"] == "OW-1"


def test_facade_oracle_failure_returns_503(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")

    def fail():
        raise oracledb.Error("ORA-12541: no listener")

    monkeypatch.setattr(facade_module.oracle, "list_plans", fail)
    response = app.test_client().get("/api/v1/billing/plans")
    assert response.status_code == 503
    assert response.get_json() == {
        "error": "legacy estate unavailable",
        "detail": "the Oracle billing estate is not reachable",
    }


class DuplicateError(oracledb.Error):
    pass


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        raise DuplicateError("ORA-00001: unique constraint violated")


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor()

    def commit(self):
        return None


def test_internal_ingest_duplicate(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(facade_module.oracle, "ensure_tenant", lambda *args: None)
    monkeypatch.setattr(facade_module.oracle, "oracle_connect", lambda: FakeConnection())
    response = app.test_client().post(
        "/internal/usage/events",
        json={
            "event_id": "event-1",
            "tenant_id": "tenant-1",
            "email": "tenant@example.com",
            "kind": "api",
            "units": 1,
            "occurred_at": "2026-02-10T10:00:00Z",
        },
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "duplicate"}
