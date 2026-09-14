"""Tests for the authentication middleware with REQUIRE_AUTH enabled."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.config import AppConfig, AuthConfig
from app.main import create_app

JWT_SECRET = "test-jwt-secret-that-is-at-least-48-bytes-long-for-hs384"
SERVICE_TOKEN = "test-service-token"

SEARCH_URL = "/api/v1/search/?q=test"
INDEX_URL = "/api/v1/search/index/document"
REINDEX_URL = "/api/v1/search/reindex"

DOCUMENT = {"id": "doc-1", "title": "Doc", "content": "body", "owner_id": "user-1"}


def _jwt(sub: str = "user-1", secret: str = JWT_SECRET, alg: str = "HS256") -> str:
    return jwt.encode({"sub": sub}, secret, algorithm=alg)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def secured_client(app_config: AppConfig, mock_meilisearch_client: MagicMock):
    """Flask test client for an app with authentication enforced."""
    config = dataclasses.replace(
        app_config,
        auth=AuthConfig(service_token=SERVICE_TOKEN, require_auth=True, jwt_secret=JWT_SECRET),
    )
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        flask_app = create_app(config)
        flask_app.config["TESTING"] = True
        yield flask_app.test_client()


class TestPublicEndpoints:
    def test_health_needs_no_auth(self, secured_client):
        assert secured_client.get("/health").status_code == 200


class TestUserEndpoints:
    def test_no_credentials_rejected(self, secured_client):
        response = secured_client.get(SEARCH_URL)
        assert response.status_code == 401
        assert response.get_json() == {"error": "unauthorized"}

    def test_forged_user_id_header_alone_rejected(self, secured_client):
        """A caller reaching the pod directly cannot authenticate with X-User-ID."""
        response = secured_client.get(SEARCH_URL, headers={"X-User-ID": "victim"})
        assert response.status_code == 401

    def test_jwt_signed_with_wrong_secret_rejected(self, secured_client):
        response = secured_client.get(SEARCH_URL, headers=_bearer(_jwt(secret="not-the-secret-but-also-32-bytes-long!!")))
        assert response.status_code == 401

    def test_unsigned_jwt_rejected(self, secured_client):
        token = jwt.encode({"sub": "user-1"}, "", algorithm="none")
        response = secured_client.get(SEARCH_URL, headers=_bearer(token))
        assert response.status_code == 401

    def test_malformed_bearer_rejected(self, secured_client):
        response = secured_client.get(SEARCH_URL, headers={"Authorization": "Bearer"})
        assert response.status_code == 401

    def test_valid_jwt_accepted(self, secured_client):
        response = secured_client.get(SEARCH_URL, headers=_bearer(_jwt()))
        assert response.status_code == 200

    def test_valid_jwt_hs384_accepted(self, secured_client):
        response = secured_client.get(SEARCH_URL, headers=_bearer(_jwt(alg="HS384")))
        assert response.status_code == 200

    def test_owner_scope_comes_from_jwt_not_header(self, secured_client, mock_meilisearch_client):
        """X-User-ID is ignored: results are scoped to the JWT subject."""
        mock_index = mock_meilisearch_client.index.return_value
        response = secured_client.get(
            SEARCH_URL,
            headers={**_bearer(_jwt(sub="attacker")), "X-User-ID": "victim"},
        )
        assert response.status_code == 200
        filters = [str(call.kwargs.get("opt_params") or call.args) for call in mock_index.search.call_args_list]
        assert any('owner_id = "attacker"' in f for f in filters)
        assert not any("victim" in f for f in filters)

    def test_advanced_search_owner_scope_comes_from_jwt(self, secured_client, mock_meilisearch_client):
        mock_index = mock_meilisearch_client.index.return_value
        response = secured_client.post(
            "/api/v1/search/advanced",
            headers={**_bearer(_jwt(sub="attacker")), "X-User-ID": "victim"},
            json={"q": "report", "owner_id": "victim"},
        )
        assert response.status_code == 200
        filters = [str(call.kwargs.get("opt_params") or call.args) for call in mock_index.search.call_args_list]
        assert any('owner_id = "attacker"' in f for f in filters)
        assert not any("victim" in f for f in filters)

    def test_service_token_accepted_on_user_endpoint(self, secured_client):
        response = secured_client.get(SEARCH_URL, headers=_bearer(SERVICE_TOKEN))
        assert response.status_code == 200


class TestInternalEndpoints:
    def test_no_credentials_rejected(self, secured_client):
        assert secured_client.post(INDEX_URL, json=DOCUMENT).status_code == 401
        assert secured_client.post(REINDEX_URL).status_code == 401

    def test_forged_user_id_header_rejected(self, secured_client):
        response = secured_client.post(INDEX_URL, json=DOCUMENT, headers={"X-User-ID": "user-1"})
        assert response.status_code == 401

    def test_user_jwt_forbidden(self, secured_client):
        """A valid end-user token must not reach indexing endpoints."""
        headers = _bearer(_jwt())
        assert secured_client.post(INDEX_URL, json=DOCUMENT, headers=headers).status_code == 403
        assert secured_client.post(REINDEX_URL, headers=headers).status_code == 403
        assert secured_client.delete("/api/v1/search/index/document/doc-1", headers=headers).status_code == 403

    def test_wrong_service_token_rejected(self, secured_client):
        response = secured_client.post(INDEX_URL, json=DOCUMENT, headers=_bearer("wrong-token"))
        assert response.status_code == 401

    def test_service_token_accepted(self, secured_client):
        response = secured_client.post(INDEX_URL, json=DOCUMENT, headers=_bearer(SERVICE_TOKEN))
        assert response.status_code == 201
        assert secured_client.post(REINDEX_URL, headers=_bearer(SERVICE_TOKEN)).status_code == 200


class TestMissingServiceToken:
    def test_internal_endpoints_unreachable_without_configured_token(
        self, app_config: AppConfig, mock_meilisearch_client: MagicMock
    ):
        config = dataclasses.replace(
            app_config,
            auth=AuthConfig(service_token="", require_auth=True, jwt_secret=JWT_SECRET),
        )
        with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
            mock_cls.return_value = mock_meilisearch_client
            client = create_app(config).test_client()
            # An empty bearer must not match an empty configured token.
            assert client.post(INDEX_URL, json=DOCUMENT, headers={"Authorization": "Bearer "}).status_code == 401
            assert client.post(INDEX_URL, json=DOCUMENT, headers=_bearer(_jwt())).status_code == 403
