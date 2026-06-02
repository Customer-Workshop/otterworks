"""Tests for the authentication middleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app


@pytest.fixture()
def auth_config() -> AppConfig:
    """Config with auth enabled and a service token."""
    return AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-docs",
            files_index="test-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(service_token="test-service-token", require_auth=True),
    )


@pytest.fixture()
def no_auth_config() -> AppConfig:
    """Config with auth disabled."""
    return AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-docs",
            files_index="test-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(service_token="", require_auth=False),
    )


def _create_app(config):
    from unittest.mock import MagicMock
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.health.return_value = {"status": "available"}
        mock_client.get_index.side_effect = None
        mock_cls.return_value = mock_client
        app = create_app(config)
        app.config["TESTING"] = True
        return app


class TestAuthMiddleware:
    def test_health_endpoint_is_public(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_metrics_endpoint_is_public(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_protected_endpoint_rejects_no_auth(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get("/api/v1/search")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "unauthorized"

    def test_protected_endpoint_accepts_service_token(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get(
            "/api/v1/search",
            headers={"Authorization": "Bearer test-service-token"},
        )
        # Should not return 401 - the request passes auth
        assert resp.status_code != 401

    def test_protected_endpoint_accepts_x_user_id(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get(
            "/api/v1/search",
            headers={"X-User-ID": "user-123"},
        )
        assert resp.status_code != 401

    def test_protected_endpoint_rejects_wrong_token(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get(
            "/api/v1/search",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_auth_disabled_allows_all(self, no_auth_config: AppConfig):
        app = _create_app(no_auth_config)
        client = app.test_client()
        resp = client.get("/api/v1/search")
        assert resp.status_code != 401

    def test_empty_x_user_id_rejected(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get(
            "/api/v1/search",
            headers={"X-User-ID": "   "},
        )
        assert resp.status_code == 401

    def test_bearer_prefix_case_insensitive(self, auth_config: AppConfig):
        app = _create_app(auth_config)
        client = app.test_client()
        resp = client.get(
            "/api/v1/search",
            headers={"Authorization": "BEARER test-service-token"},
        )
        assert resp.status_code != 401
