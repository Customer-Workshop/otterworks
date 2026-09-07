"""Tests for identity resolution and owner scoping of search results."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app

SECRET = "unit-test-jwt-secret"
SERVICE_TOKEN = "unit-test-service-token"


def _make_app(mock_meilisearch_client: MagicMock, auth: AuthConfig):
    config = AppConfig(
        service_name="search-service-test",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-otterworks-documents",
            files_index="test-otterworks-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=auth,
    )
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        app = create_app(config)
    app.config["TESTING"] = True
    return app


def _token(user_id: str, secret: str = SECRET, claim: str = "sub") -> str:
    return jwt.encode({claim: user_id, "exp": int(time.time()) + 300}, secret, algorithm="HS256")


def _filters(mock_meilisearch_client: MagicMock) -> list[str]:
    mock_index = mock_meilisearch_client.index.return_value
    return [call.args[1].get("filter", "") for call in mock_index.search.call_args_list]


@pytest.fixture()
def jwt_client(mock_meilisearch_client):
    app = _make_app(
        mock_meilisearch_client,
        AuthConfig(service_token=SERVICE_TOKEN, require_auth=True, jwt_secret=SECRET),
    )
    return app.test_client()


@pytest.fixture()
def legacy_client(mock_meilisearch_client):
    app = _make_app(
        mock_meilisearch_client,
        AuthConfig(service_token="", require_auth=True, jwt_secret=""),
    )
    return app.test_client()


class TestJwtIdentity:
    def test_missing_credentials_rejected(self, jwt_client):
        assert jwt_client.get("/api/v1/search/?q=test").status_code == 401

    def test_bare_x_user_id_is_not_an_identity(self, jwt_client, mock_meilisearch_client):
        """With a JWT secret configured, a request header alone never authenticates."""
        resp = jwt_client.get("/api/v1/search/?q=test", headers={"X-User-ID": "victim"})
        assert resp.status_code == 401
        mock_meilisearch_client.index.return_value.search.assert_not_called()

    def test_forged_jwt_rejected(self, jwt_client):
        resp = jwt_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {_token('attacker', secret='wrong')}"},
        )
        assert resp.status_code == 401

    def test_unsigned_jwt_rejected(self, jwt_client):
        token = jwt.encode({"sub": "attacker"}, "", algorithm="none")
        resp = jwt_client.get(
            "/api/v1/search/?q=test", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    def test_jwt_without_subject_rejected(self, jwt_client):
        token = jwt.encode({"email": "x@example.com"}, SECRET, algorithm="HS256")
        resp = jwt_client.get(
            "/api/v1/search/?q=test", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    def test_search_scoped_to_jwt_subject(self, jwt_client, mock_meilisearch_client):
        resp = jwt_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {_token('user-a')}"},
        )
        assert resp.status_code == 200
        filters = _filters(mock_meilisearch_client)
        assert filters and all('owner_id = "user-a"' in f for f in filters)

    def test_user_id_claim_fallback(self, jwt_client, mock_meilisearch_client):
        resp = jwt_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {_token('user-b', claim='user_id')}"},
        )
        assert resp.status_code == 200
        assert all('owner_id = "user-b"' in f for f in _filters(mock_meilisearch_client))

    def test_spoofed_header_ignored_when_jwt_present(self, jwt_client, mock_meilisearch_client):
        """X-User-ID pointing at another tenant must not widen or move the scope."""
        resp = jwt_client.get(
            "/api/v1/search/?q=test",
            headers={
                "Authorization": f"Bearer {_token('user-a')}",
                "X-User-ID": "victim",
            },
        )
        assert resp.status_code == 200
        filters = _filters(mock_meilisearch_client)
        assert filters
        for f in filters:
            assert 'owner_id = "user-a"' in f
            assert "victim" not in f

    def test_advanced_search_scoped_to_jwt_not_body(self, jwt_client, mock_meilisearch_client):
        resp = jwt_client.post(
            "/api/v1/search/advanced",
            json={"q": "report", "owner_id": "victim"},
            headers={
                "Authorization": f"Bearer {_token('user-a')}",
                "X-User-ID": "victim",
            },
        )
        assert resp.status_code == 200
        filters = _filters(mock_meilisearch_client)
        assert filters
        for f in filters:
            assert 'owner_id = "user-a"' in f
            assert "victim" not in f

    def test_suggest_scoped_to_jwt_subject(self, jwt_client, mock_meilisearch_client):
        resp = jwt_client.get(
            "/api/v1/search/suggest?q=rep",
            headers={"Authorization": f"Bearer {_token('user-a')}"},
        )
        assert resp.status_code == 200
        filters = _filters(mock_meilisearch_client)
        assert filters and all(f == 'owner_id = "user-a"' for f in filters)

    def test_service_token_may_act_for_user(self, jwt_client, mock_meilisearch_client):
        resp = jwt_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}", "X-User-ID": "user-z"},
        )
        assert resp.status_code == 200
        assert all('owner_id = "user-z"' in f for f in _filters(mock_meilisearch_client))

    def test_health_is_public(self, jwt_client):
        assert jwt_client.get("/health").status_code == 200


class TestLegacyGatewayHeaderMode:
    """Without JWT_SECRET the gateway-injected header is the only identity source."""

    def test_header_required(self, legacy_client):
        assert legacy_client.get("/api/v1/search/?q=test").status_code == 401

    def test_header_scopes_results(self, legacy_client, mock_meilisearch_client):
        resp = legacy_client.get("/api/v1/search/?q=test", headers={"X-User-ID": "user-a"})
        assert resp.status_code == 200
        assert all('owner_id = "user-a"' in f for f in _filters(mock_meilisearch_client))


class TestAuthNotRequired:
    """REQUIRE_AUTH=false never rejects, but still scopes when an identity is present."""

    @pytest.fixture()
    def open_client(self, mock_meilisearch_client):
        app = _make_app(
            mock_meilisearch_client,
            AuthConfig(service_token="", require_auth=False, jwt_secret=SECRET),
        )
        return app.test_client()

    def test_anonymous_allowed_unscoped(self, open_client, mock_meilisearch_client):
        assert open_client.get("/api/v1/search/?q=test").status_code == 200
        assert all("owner_id" not in f for f in _filters(mock_meilisearch_client))

    def test_jwt_scopes_results(self, open_client, mock_meilisearch_client):
        resp = open_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {_token('user-a')}", "X-User-ID": "victim"},
        )
        assert resp.status_code == 200
        assert all('owner_id = "user-a"' in f for f in _filters(mock_meilisearch_client))

    def test_gateway_header_scopes_results(self, open_client, mock_meilisearch_client):
        resp = open_client.get("/api/v1/search/?q=test", headers={"X-User-ID": "user-b"})
        assert resp.status_code == 200
        assert all('owner_id = "user-b"' in f for f in _filters(mock_meilisearch_client))
