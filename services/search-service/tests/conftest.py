"""Pytest fixtures for Search Service tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app
from app.services.meilisearch_client import MeiliSearchService


@pytest.fixture()
def app_config() -> AppConfig:
    """Create a test AppConfig with auth disabled."""
    return AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-otterworks-documents",
            files_index="test-otterworks-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(service_token="", require_auth=False),
    )


@pytest.fixture()
def mock_meilisearch_client() -> MagicMock:
    """Create a mock meilisearch.Client."""
    mock = MagicMock()

    mock_health = {"status": "available"}
    mock.health.return_value = mock_health

    mock_task = MagicMock()
    mock_task.task_uid = 1
    mock_task_result = MagicMock()
    mock_task_result.status = "succeeded"
    mock.wait_for_task.return_value = mock_task_result

    mock_index = MagicMock()
    mock_index.add_documents.return_value = mock_task
    mock_index.delete_document.return_value = mock_task
    mock_index.search.return_value = {"hits": [], "estimatedTotalHits": 0}
    mock.index.return_value = mock_index

    mock.create_index.return_value = mock_task
    mock.delete_index.return_value = mock_task
    mock.get_index.side_effect = None

    return mock


@pytest.fixture()
def app(app_config: AppConfig, mock_meilisearch_client: MagicMock):
    """Create a FastAPI test app with mocked MeiliSearch."""
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        fastapi_app = create_app(app_config)
        # Manually set the search_service on app state for tests
        # (lifespan doesn't run in tests using TestClient directly)
        search_service = MeiliSearchService(app_config.meilisearch)
        fastapi_app.state.search_service = search_service
        yield fastapi_app


@pytest.fixture()
def client(app):
    """Create a sync test client using httpx."""
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.fixture()
def meilisearch_service(app_config: AppConfig, mock_meilisearch_client: MagicMock) -> MeiliSearchService:
    """Create a MeiliSearchService with a mocked client."""
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        service = MeiliSearchService(app_config.meilisearch)
        return service
