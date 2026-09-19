import sys
from datetime import date, timedelta
from pathlib import Path

import oracledb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import backends
import facade as facade_module
from app import app


def test_facade_requires_identity(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().get("/api/v1/billing/me")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/api/v1/billing/me?on=2026-02-31", {"X-User-ID": "tenant"}),
        ("/api/v1/billing/entitlement?on=not-a-date", {"X-User-ID": "tenant"}),
        (
            "/api/v1/billing/usage?period_start=2026-03-01&period_end=2026-02-01",
            {"X-User-ID": "tenant"},
        ),
        (
            "/api/v1/billing/usage?period_start=2026-02-01&period_end=not-a-date",
            {"X-User-ID": "tenant"},
        ),
        (
            "/api/v1/billing/admin/overdue?as_of=tomorrow",
            {"X-User-ID": "tenant", "X-User-Roles": "ADMIN"},
        ),
        (
            "/api/v1/billing/admin/dunning?as_of=tomorrow",
            {"X-User-ID": "tenant", "X-User-Roles": "ADMIN"},
        ),
    ],
)
def test_invalid_date_query_params_fail_before_oracle(monkeypatch, path, headers):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(
        facade_module,
        "_ensure",
        lambda _: pytest.fail("Oracle was touched"),
    )
    monkeypatch.setattr(
        facade_module.oracle,
        "overdue",
        lambda _: pytest.fail("Oracle was touched"),
    )
    monkeypatch.setattr(
        facade_module.oracle,
        "query",
        lambda *_args, **_kwargs: pytest.fail("Oracle was touched"),
    )
    response = app.test_client().get(path, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid date"


def test_admin_facade_requires_role(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().get(
        "/api/v1/billing/admin/overdue",
        headers={"X-User-ID": "tenant"},
    )
    assert response.status_code == 403


def test_admin_overdue_maps_total_to_amount(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(
        facade_module.oracle,
        "overdue",
        lambda as_of: [
            {
                "tenant_id": "tenant-1",
                "invoice_id": "invoice-1",
                "total": "25.00",
                "days_overdue": 12,
            }
        ],
    )
    response = app.test_client().get(
        "/api/v1/billing/admin/overdue",
        headers={"X-User-ID": "tenant", "X-User-Roles": "ADMIN"},
    )
    assert response.status_code == 200
    assert response.get_json() == [
        {
            "tenant_id": "tenant-1",
            "invoice_id": "invoice-1",
            "total": "25.00",
            "amount": "25.00",
            "days_overdue": 12,
        }
    ]


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
    monkeypatch.setenv("USAGE_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(facade_module.oracle, "ensure_tenant", lambda *args: None)
    monkeypatch.setattr(facade_module.oracle, "oracle_connect", lambda: FakeConnection())
    response = app.test_client().post(
        "/internal/usage/events",
        json={
            "event_id": "00000000-0000-0000-0000-000000000001",
            "tenant_id": "tenant-1",
            "email": "tenant@example.com",
            "kind": "api",
            "units": 1,
            "occurred_at": "2026-02-10T10:00:00Z",
        },
        headers={"X-Internal-Token": "test-token"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "duplicate"}


def test_internal_ingest_requires_token(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setenv("USAGE_INTERNAL_TOKEN", "test-token")
    response = app.test_client().post("/internal/usage/events", json={})
    assert response.status_code == 401


def test_internal_ingest_rejects_invalid_payload_before_oracle(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setenv("USAGE_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(
        facade_module.oracle,
        "oracle_connect",
        lambda: (_ for _ in ()).throw(AssertionError("Oracle touched")),
    )
    response = app.test_client().post(
        "/internal/usage/events",
        headers={"X-Internal-Token": "test-token"},
        json={
            "event_id": "00000000-0000-0000-0000-000000000001",
            "tenant_id": "tenant-1",
            "kind": "invalid",
            "units": 1,
            "occurred_at": "not-a-date",
        },
    )
    assert response.status_code == 400


def test_internal_ingest_rejects_non_uuid_event_id_before_oracle(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setenv("USAGE_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(
        facade_module.oracle,
        "oracle_connect",
        lambda: (_ for _ in ()).throw(AssertionError("Oracle touched")),
    )
    response = app.test_client().post(
        "/internal/usage/events",
        headers={"X-Internal-Token": "test-token"},
        json={
            "event_id": "x" * 64,
            "tenant_id": "tenant-1",
            "kind": "api",
            "units": 1,
            "occurred_at": "2026-02-10T10:00:00Z",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["detail"] == "event_id must be a canonical UUID"


def test_plan_change_rejects_missing_field_before_oracle(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    called = False

    def list_plans():
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(facade_module.oracle, "list_plans", list_plans)
    response = app.test_client().post(
        "/api/v1/billing/plan-change",
        headers={"X-User-ID": "tenant"},
        json={"effective_on": (date.today() + timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid plan change"
    assert called is False


def test_plan_change_rejects_bad_date(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().post(
        "/api/v1/billing/plan-change",
        headers={"X-User-ID": "tenant"},
        json={"plan_id": "p1", "effective_on": "not-a-date"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid plan change"


def test_plan_change_rejects_past_date(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    response = app.test_client().post(
        "/api/v1/billing/plan-change",
        headers={"X-User-ID": "tenant"},
        json={"plan_id": "p1", "effective_on": "2020-01-01"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid plan change"


def test_plan_change_rejects_unknown_plan(monkeypatch):
    monkeypatch.setenv("BILLING_BACKEND", "oracle")
    monkeypatch.setattr(facade_module.oracle, "list_plans", lambda: [{"plan_id": "p2"}])
    response = app.test_client().post(
        "/api/v1/billing/plan-change",
        headers={"X-User-ID": "tenant"},
        json={"plan_id": "p1", "effective_on": (date.today() + timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid plan change"
