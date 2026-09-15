from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.main as main
from app.domain import EntitlementRow, SubscriptionRow

TENANT_A = UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = UUID("00000000-0000-0000-0000-00000000000b")
PLAN = UUID("10000000-0000-0000-0000-000000000002")
SERVICE_TOKEN = "test-service-token"
JWT_SECRET = "test-jwt-secret-that-is-at-least-32-bytes-long"
USER_A = "user-a"
MEMBERSHIPS = {(TENANT_A, USER_A)}
PAYLOAD = {"plan_id": str(PLAN), "effective_on": "2026-03-01"}


def access_token(
    user_id: str = USER_A, secret: str = JWT_SECRET, token_type: str = "access"
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeConnection:
    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeRepository:
    def __init__(self, _connection: object) -> None:
        pass

    def is_tenant_member(self, tenant_id: UUID, user_id: str) -> bool:
        return (tenant_id, user_id) in MEMBERSHIPS

    def find_entitlements(self, tenant_id: UUID) -> list[EntitlementRow]:
        return [
            EntitlementRow(
                tenant_id=tenant_id,
                plan_code="STARTER",
                tier="starter",
                monthly_fee=Decimal("49.00"),
                included_units=100,
                subscription_status="active",
                ends_on=None,
                starts_on=date(2026, 1, 1),
            )
        ]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    def fake_change_plan(
        _repository: object, tenant_id: UUID, plan_id: UUID, starts_on: date
    ) -> tuple[list[SubscriptionRow], SubscriptionRow]:
        created = SubscriptionRow(
            UUID("20000000-0000-0000-0000-000000000003"),
            tenant_id,
            plan_id,
            starts_on,
            None,
            "active",
            None,
        )
        return [created], created

    monkeypatch.setattr(main, "migrate", lambda: None)
    monkeypatch.setattr(main, "connect", FakeConnection)
    monkeypatch.setattr(main, "PostgresPlansRepository", FakeRepository)
    monkeypatch.setattr(main, "change_plan", fake_change_plan)
    monkeypatch.setattr(auth, "connect", FakeConnection)
    monkeypatch.setattr(auth, "PostgresPlansRepository", FakeRepository)
    monkeypatch.setattr(main.settings, "service_token", SERVICE_TOKEN)
    monkeypatch.setattr(main.settings, "jwt_secret", JWT_SECRET)
    with TestClient(main.app) as test_client:
        yield test_client


def test_anonymous_caller_is_rejected(client: TestClient) -> None:
    read = client.get(f"/api/tenants/{TENANT_A}/entitlement", params={"on": "2026-02-28"})
    write = client.post(f"/api/tenants/{TENANT_A}/plan-change", json=PAYLOAD)

    assert read.status_code == 401
    assert write.status_code == 401


def test_user_cannot_read_or_change_another_tenant(client: TestClient) -> None:
    headers = bearer(access_token())
    read = client.get(
        f"/api/tenants/{TENANT_B}/entitlement", params={"on": "2026-02-28"}, headers=headers
    )
    write = client.post(f"/api/tenants/{TENANT_B}/plan-change", json=PAYLOAD, headers=headers)

    assert read.status_code == 403
    assert write.status_code == 403


def test_user_can_act_on_own_tenant(client: TestClient) -> None:
    headers = bearer(access_token())
    read = client.get(
        f"/api/tenants/{TENANT_A}/entitlement", params={"on": "2026-02-28"}, headers=headers
    )
    write = client.post(f"/api/tenants/{TENANT_A}/plan-change", json=PAYLOAD, headers=headers)

    assert read.status_code == 200
    assert read.json()["tenant_id"] == str(TENANT_A)
    assert write.status_code == 200


def test_forwarded_identity_headers_are_not_trusted(client: TestClient) -> None:
    forged = {"X-User-ID": USER_A, "X-Tenant-ID": str(TENANT_A)}
    read = client.get(
        f"/api/tenants/{TENANT_A}/entitlement", params={"on": "2026-02-28"}, headers=forged
    )
    write = client.post(f"/api/tenants/{TENANT_A}/plan-change", json=PAYLOAD, headers=forged)

    assert read.status_code == 401
    assert write.status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        access_token(secret="some-other-secret"),
        access_token(token_type="refresh"),
        jwt.encode(
            {"sub": USER_A, "type": "access", "exp": datetime(2020, 1, 1, tzinfo=UTC)},
            JWT_SECRET,
            algorithm="HS256",
        ),
        "not-a-jwt",
    ],
)
def test_invalid_user_tokens_are_rejected(client: TestClient, token: str) -> None:
    response = client.get(
        f"/api/tenants/{TENANT_A}/entitlement", params={"on": "2026-02-28"}, headers=bearer(token)
    )

    assert response.status_code == 401


def test_internal_reset_requires_service_credential(client: TestClient, monkeypatch) -> None:
    calls = 0

    def fake_reset() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(main, "reset", fake_reset)
    monkeypatch.setattr(main.settings, "allow_internal_reset", True)

    anonymous = client.post("/internal/reset")
    as_user = client.post("/internal/reset", headers=bearer(access_token()))
    as_service = client.post("/internal/reset", headers=bearer(SERVICE_TOKEN))

    assert anonymous.status_code == 401
    assert as_user.status_code == 403
    assert as_service.status_code == 204
    assert calls == 1


def test_user_tokens_are_rejected_when_no_jwt_secret_is_configured(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(main.settings, "jwt_secret", "")
    response = client.get(
        f"/api/tenants/{TENANT_A}/entitlement",
        params={"on": "2026-02-28"},
        headers=bearer(access_token()),
    )

    assert response.status_code == 401


def test_service_token_may_act_on_any_tenant(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
    read = client.get(
        f"/api/tenants/{TENANT_B}/entitlement", params={"on": "2026-02-28"}, headers=headers
    )
    write = client.post(f"/api/tenants/{TENANT_B}/plan-change", json=PAYLOAD, headers=headers)

    assert read.status_code == 200
    assert write.status_code == 200


def test_wrong_service_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        f"/api/tenants/{TENANT_A}/entitlement",
        params={"on": "2026-02-28"},
        headers={"Authorization": "Bearer wrong-token", "X-User-ID": USER_A},
    )

    assert response.status_code == 401


def test_bearer_token_is_ignored_when_no_service_token_is_configured(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(main.settings, "service_token", "")
    response = client.get(
        f"/api/tenants/{TENANT_B}/entitlement",
        params={"on": "2026-02-28"},
        headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
    )

    assert response.status_code == 401
