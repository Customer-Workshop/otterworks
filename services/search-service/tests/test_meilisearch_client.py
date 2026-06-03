"""Tests for the MeiliSearch client service."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.config import MeiliSearchConfig
from app.services.meilisearch_client import (
    MeiliSearchService,
    get_search_analytics,
    record_search_analytics,
    _search_analytics,
    _analytics_lock,
)


@pytest.fixture(autouse=True)
def reset_analytics():
    """Reset analytics state between tests."""
    with _analytics_lock:
        _search_analytics["queries"] = []
        _search_analytics["total_searches"] = 0
        _search_analytics["total_results"] = 0
    yield


@pytest.fixture()
def config() -> MeiliSearchConfig:
    return MeiliSearchConfig(
        url="http://localhost:7700",
        api_key="test-key",
        documents_index="test-documents",
        files_index="test-files",
    )


@pytest.fixture()
def mock_client() -> MagicMock:
    mock = MagicMock()
    mock.health.return_value = {"status": "available"}
    mock_task = MagicMock()
    mock_task.task_uid = 1
    mock.create_index.return_value = mock_task
    mock.wait_for_task.return_value = MagicMock(status="succeeded")
    mock_index = MagicMock()
    mock_index.search.return_value = {"hits": [], "estimatedTotalHits": 0}
    mock_index.add_documents.return_value = mock_task
    mock_index.delete_document.return_value = mock_task
    mock.index.return_value = mock_index
    mock.get_index.side_effect = None
    return mock


@pytest.fixture()
def service(config: MeiliSearchConfig, mock_client: MagicMock) -> MeiliSearchService:
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_client
        svc = MeiliSearchService(config)
        return svc


class TestRecordSearchAnalytics:
    """Tests for the record_search_analytics function."""

    def test_records_a_query(self):
        record_search_analytics("hello", 5)

        analytics = get_search_analytics()
        assert analytics.total_searches == 1
        assert analytics.avg_results_per_query == 5.0

    def test_tracks_multiple_queries(self):
        record_search_analytics("hello", 5)
        record_search_analytics("world", 3)
        record_search_analytics("hello", 2)

        analytics = get_search_analytics()
        assert analytics.total_searches == 3
        assert analytics.avg_results_per_query == pytest.approx(3.33, abs=0.01)

    def test_tracks_popular_queries(self):
        for _ in range(10):
            record_search_analytics("popular", 5)
        for _ in range(3):
            record_search_analytics("less popular", 2)

        analytics = get_search_analytics()
        assert analytics.popular_queries[0]["query"] == "popular"
        assert analytics.popular_queries[0]["count"] == 10

    def test_tracks_zero_result_queries(self):
        record_search_analytics("no results", 0)
        record_search_analytics("no results", 0)
        record_search_analytics("has results", 5)

        analytics = get_search_analytics()
        assert len(analytics.zero_result_queries) == 1
        assert analytics.zero_result_queries[0]["query"] == "no results"
        assert analytics.zero_result_queries[0]["count"] == 2

    def test_empty_analytics(self):
        analytics = get_search_analytics()
        assert analytics.total_searches == 0
        assert analytics.avg_results_per_query == 0.0
        assert analytics.popular_queries == []
        assert analytics.zero_result_queries == []


class TestMeiliSearchServicePing:
    """Tests for the ping method."""

    def test_ping_returns_true_when_healthy(self, service: MeiliSearchService, mock_client: MagicMock):
        result = service.ping()
        assert result is True
        mock_client.health.assert_called_once()

    def test_ping_returns_false_on_error(self, service: MeiliSearchService, mock_client: MagicMock):
        mock_client.health.side_effect = Exception("Connection refused")
        result = service.ping()
        assert result is False


class TestMeiliSearchServiceEscape:
    """Tests for the _escape static method."""

    def test_escapes_quotes(self):
        result = MeiliSearchService._escape('hello "world"')
        assert result == 'hello \\"world\\"'

    def test_escapes_backslashes(self):
        result = MeiliSearchService._escape("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_no_escaping_needed(self):
        result = MeiliSearchService._escape("simple text")
        assert result == "simple text"

    def test_both_backslash_and_quote(self):
        result = MeiliSearchService._escape('a\\"b')
        assert result == 'a\\\\\\"b'


class TestMeiliSearchServiceEnsureIndices:
    """Tests for ensure_indices."""

    def test_creates_indices_when_not_exist(self, config: MeiliSearchConfig):
        import meilisearch.errors

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"message":"Index not found","code":"index_not_found","type":"invalid_request","link":"https://docs.meilisearch.com/errors#index_not_found"}'
        mock_client = MagicMock()
        mock_client.get_index.side_effect = meilisearch.errors.MeilisearchApiError(
            "not_found", mock_response
        )
        mock_task = MagicMock()
        mock_task.task_uid = 1
        mock_client.create_index.return_value = mock_task
        mock_client.wait_for_task.return_value = MagicMock(status="succeeded")
        mock_index = MagicMock()
        mock_client.index.return_value = mock_index

        with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
            mock_cls.return_value = mock_client
            svc = MeiliSearchService(config)
            svc.ensure_indices()

        assert mock_client.create_index.call_count == 2

    def test_skips_creation_when_indices_exist(self, service: MeiliSearchService, mock_client: MagicMock):
        mock_client.get_index.side_effect = None
        mock_client.get_index.return_value = MagicMock()

        service.ensure_indices()

        mock_client.create_index.assert_not_called()
