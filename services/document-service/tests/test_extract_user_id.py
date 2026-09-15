"""Unit tests for the request identity extraction in app.api.documents."""

import uuid

import jwt
import pytest
from starlette.requests import Request

from app.api.documents import _extract_user_id

SECRET = "unit-test-secret-padded-to-32-chars!!"  # noqa: S105


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


@pytest.fixture
def with_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


@pytest.fixture
def without_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)


@pytest.mark.parametrize("claim", ["user_id", "sub"])
@pytest.mark.parametrize("algorithm", ["HS256", "HS384"])
def test_valid_jwt_yields_user_id(with_secret, claim, algorithm):
    user_id = uuid.uuid4()
    token = jwt.encode({claim: str(user_id)}, SECRET, algorithm=algorithm)
    assert _extract_user_id(_request({"Authorization": f"Bearer {token}"})) == user_id


def test_user_id_claim_wins_over_sub(with_secret):
    user_id, sub = uuid.uuid4(), uuid.uuid4()
    token = jwt.encode({"user_id": str(user_id), "sub": str(sub)}, SECRET, algorithm="HS256")
    assert _extract_user_id(_request({"Authorization": f"Bearer {token}"})) == user_id


def test_jwt_signed_with_wrong_secret_is_rejected(with_secret):
    token = jwt.encode({"user_id": str(uuid.uuid4())}, "other-secret", algorithm="HS256")
    assert _extract_user_id(_request({"Authorization": f"Bearer {token}"})) is None


def test_jwt_without_identity_claim_yields_none(with_secret):
    token = jwt.encode({"role": "USER"}, SECRET, algorithm="HS256")
    assert _extract_user_id(_request({"Authorization": f"Bearer {token}"})) is None


def test_jwt_with_non_uuid_identity_yields_none(with_secret):
    token = jwt.encode({"user_id": "not-a-uuid"}, SECRET, algorithm="HS256")
    assert _extract_user_id(_request({"Authorization": f"Bearer {token}"})) is None


def test_garbage_token_yields_none(with_secret):
    assert _extract_user_id(_request({"Authorization": "Bearer nope"})) is None


def test_x_user_id_is_ignored_when_secret_configured(with_secret):
    headers = {"Authorization": "Bearer nope", "X-User-ID": str(uuid.uuid4())}
    assert _extract_user_id(_request(headers)) is None


def test_missing_or_non_bearer_authorization_yields_none(with_secret):
    assert _extract_user_id(_request({})) is None
    assert _extract_user_id(_request({"Authorization": "Basic abc"})) is None


def test_x_user_id_fallback_requires_bearer_header(without_secret):
    user_id = uuid.uuid4()
    assert _extract_user_id(_request({"X-User-ID": str(user_id)})) is None
    headers = {"Authorization": "Bearer token", "X-User-ID": str(user_id)}
    assert _extract_user_id(_request(headers)) == user_id


def test_x_user_id_fallback_rejects_non_uuid(without_secret):
    headers = {"Authorization": "Bearer token", "X-User-ID": "not-a-uuid"}
    assert _extract_user_id(_request(headers)) is None
    assert _extract_user_id(_request({"Authorization": "Bearer token"})) is None
