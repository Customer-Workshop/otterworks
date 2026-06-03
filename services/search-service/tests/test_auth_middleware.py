"""Tests for the authentication middleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app


@pytest.fixture()
def auth_config() -> AppConfig:
    """Create a test AppConfig with auth ENABLED."""
    return AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-documents",
            files_index="test-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(service_token="test-service-token", require_auth=True),
    )


@pytest.fixture()
def auth_app(auth_config: AppConfig, mock_meilisearch_client):
    """Create a Flask test app with auth enabled."""
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        flask_app = create_app(auth_config)
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture()
def mock_meilisearch_client() -> MagicMock:
    """Create a mock meilisearch.Client."""
    mock = MagicMock()
    mock.health.return_value = {"status": "available"}
    mock_task = MagicMock()
    mock_task.task_uid = 1
    mock.create_index.return_value = mock_task
    mock.wait_for_task.return_value = MagicMock(status="succeeded")
    mock_index = MagicMock()
    mock_index.search.return_value = {"hits": [], "estimatedTotalHits": 0}
    mock.index.return_value = mock_index
    mock.get_index.side_effect = None
    return mock


@pytest.fixture()
def auth_client(auth_app):
    """Create a Flask test client with auth enabled."""
    return auth_app.test_client()


class TestAuthMiddleware:
    """Tests for the require_auth middleware."""

    def test_health_endpoint_is_public(self, auth_client):
        response = auth_client.get("/health")
        assert response.status_code == 200

    def test_metrics_endpoint_is_public(self, auth_client):
        response = auth_client.get("/metrics")
        # metrics endpoint should not return 401
        assert response.status_code != 401

    def test_rejects_unauthenticated_search_request(self, auth_client):
        response = auth_client.get("/api/v1/search?q=test")
        assert response.status_code == 401
        data = response.get_json()
        assert data["error"] == "unauthorized"

    def test_accepts_valid_service_token(self, auth_client):
        response = auth_client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": "Bearer test-service-token"},
        )
        # Should not be 401 - the service token should be accepted
        assert response.status_code != 401

    def test_rejects_invalid_service_token(self, auth_client):
        response = auth_client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401

    def test_accepts_x_user_id_header(self, auth_client):
        response = auth_client.get(
            "/api/v1/search?q=test",
            headers={"X-User-ID": "user-123"},
        )
        # Should not be 401 - gateway identity should be accepted
        assert response.status_code != 401

    def test_rejects_empty_x_user_id_header(self, auth_client):
        response = auth_client.get(
            "/api/v1/search?q=test",
            headers={"X-User-ID": "   "},
        )
        assert response.status_code == 401

    def test_auth_disabled_allows_all_requests(self, client):
        # Uses the default `client` fixture from conftest with auth disabled
        response = client.get("/api/v1/search?q=test")
        assert response.status_code != 401


class TestAuthDisabled:
    """Tests for when auth is disabled."""

    def test_all_endpoints_accessible(self):
        config = AppConfig(
            service_name="test",
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
        with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            mock_cls.return_value.health.return_value = {"status": "available"}
            mock_cls.return_value.get_index.side_effect = None
            mock_index = MagicMock()
            mock_index.search.return_value = {"hits": [], "estimatedTotalHits": 0}
            mock_cls.return_value.index.return_value = mock_index

            app = create_app(config)
            app.config["TESTING"] = True
            client = app.test_client()

            response = client.get("/api/v1/search?q=hello")
            assert response.status_code != 401
