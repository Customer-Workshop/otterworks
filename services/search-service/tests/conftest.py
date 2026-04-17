"""Pytest fixtures for Search Service tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import AppConfig, OpenSearchConfig, SQSConfig
from app.main import create_app
from app.services.opensearch_client import OpenSearchService


@pytest.fixture()
def app_config() -> AppConfig:
    """Create a test AppConfig."""
    return AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        opensearch=OpenSearchConfig(
            url="http://localhost:9200",
            documents_index="test-otterworks-documents",
            files_index="test-otterworks-files",
        ),
        sqs=SQSConfig(enabled=False),
    )


@pytest.fixture()
def mock_opensearch_client() -> MagicMock:
    """Create a mock OpenSearch client."""
    mock = MagicMock()
    mock.ping.return_value = True
    mock.indices.exists.return_value = True
    return mock


@pytest.fixture()
def app(app_config: AppConfig, mock_opensearch_client: MagicMock):
    """Create a Flask test app with mocked OpenSearch."""
    with patch("app.services.opensearch_client.OpenSearch") as mock_os_class:
        mock_os_class.return_value = mock_opensearch_client
        flask_app = create_app(app_config)
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture()
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture()
def opensearch_service(app_config: AppConfig, mock_opensearch_client: MagicMock) -> OpenSearchService:
    """Create an OpenSearchService with a mocked client."""
    with patch("app.services.opensearch_client.OpenSearch") as mock_os_class:
        mock_os_class.return_value = mock_opensearch_client
        service = OpenSearchService(app_config.opensearch)
        return service
