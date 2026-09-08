"""Tests for search API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.search import SUGGEST_RANKING_FLAG, _rank_suggestions


class TestSearchEndpoint:
    """Tests for GET /api/v1/search/."""

    def test_search_requires_query(self, client):
        """Search without 'q' returns 400."""
        response = client.get("/api/v1/search/")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_search_with_query(self, client, mock_meilisearch_client):
        """Search with a valid query returns results."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 1,
            "hits": [
                {
                    "id": "doc-1",
                    "title": "Test Document",
                    "content": "Some content here",
                    "type": "document",
                    "owner_id": "user-1",
                    "tags": ["test"],
                    "_formatted": {
                        "title": "Test Document",
                        "content": "Some <em>content</em> here",
                    },
                }
            ],
        }

        response = client.get("/api/v1/search/?q=test")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] >= 1
        assert len(data["results"]) >= 1
        assert data["query"] == "test"

    def test_search_with_type_filter(self, client, mock_meilisearch_client):
        """Search with type filter."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }

        response = client.get("/api/v1/search/?q=test&type=file")
        assert response.status_code == 200

    def test_search_pagination(self, client, mock_meilisearch_client):
        """Search with pagination params."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }

        response = client.get("/api/v1/search/?q=test&page=2&size=10")
        assert response.status_code == 200
        data = response.get_json()
        assert data["page"] == 2
        assert data["page_size"] == 10

    def test_search_invalid_page(self, client):
        """Search with non-numeric page returns 400."""
        response = client.get("/api/v1/search/?q=test&page=not-a-number")
        assert response.status_code == 400


class TestSuggestEndpoint:
    """Tests for GET /api/v1/search/suggest."""

    def test_suggest_short_query(self, client):
        """Suggest with query shorter than 2 chars returns empty."""
        response = client.get("/api/v1/search/suggest?q=a")
        assert response.status_code == 200
        data = response.get_json()
        assert data["suggestions"] == []

    def test_suggest_with_prefix(self, client, mock_meilisearch_client):
        """Suggest with valid prefix returns suggestions."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 2,
            "hits": [
                {"title": "Test Doc 1"},
                {"title": "Test Doc 2"},
            ],
        }

        response = client.get("/api/v1/search/suggest?q=te")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["suggestions"]) >= 1

    def test_suggest_empty_query(self, client):
        """Suggest with empty query returns empty list."""
        response = client.get("/api/v1/search/suggest?q=")
        assert response.status_code == 200
        data = response.get_json()
        assert data["suggestions"] == []

    def test_suggest_backend_failure_degrades_to_empty(self, client, mock_meilisearch_client):
        """Suggest returns 200 with no suggestions when MeiliSearch raises."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.side_effect = RuntimeError("meilisearch down")

        response = client.get("/api/v1/search/suggest?q=te")
        assert response.status_code == 200
        assert response.get_json() == {"suggestions": [], "query": "te"}


class TestSuggestRankingFlag:
    """Regression tests for GET /api/v1/search/suggest with the ranking flag set in Redis.

    The flag is the ``search-suggest-500`` chaos scenario (scripts/inject-bug.sh); it used
    to crash the handler with a 500 because suggestions carry no ``_rankingScore``.
    """

    @pytest.fixture(autouse=True)
    def ranking_flag_active(self):
        fake_redis = MagicMock()
        fake_redis.exists.return_value = 1
        with patch("app.api.search._get_redis", return_value=fake_redis):
            yield fake_redis

    def test_flag_checks_expected_key(self, client, ranking_flag_active):
        client.get("/api/v1/search/suggest?q=te")
        ranking_flag_active.exists.assert_called_with(SUGGEST_RANKING_FLAG)
        assert SUGGEST_RANKING_FLAG == "chaos:search-service:suggest_500"

    def test_suggest_with_flag_returns_suggestions(self, client, mock_meilisearch_client):
        """Suggestions without a ranking score are returned unranked, not as a 500."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 2,
            "hits": [{"title": "Test Doc 1"}, {"title": "Test Doc 2"}],
        }

        response = client.get("/api/v1/search/suggest?q=te")
        assert response.status_code == 200
        data = response.get_json()
        assert data["suggestions"] == ["Test Doc 1", "Test Doc 2"]
        assert data["query"] == "te"

    def test_suggest_with_flag_and_empty_index(self, client):
        """An empty index with the flag set yields an empty list, not a 500."""
        response = client.get("/api/v1/search/suggest?q=te")
        assert response.status_code == 200
        assert response.get_json() == {"suggestions": [], "query": "te"}

    def test_suggest_with_flag_and_backend_failure(self, client, mock_meilisearch_client):
        """MeiliSearch errors with the flag set still degrade to an empty 200."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.side_effect = RuntimeError("meilisearch down")

        response = client.get("/api/v1/search/suggest?q=te")
        assert response.status_code == 200
        assert response.get_json() == {"suggestions": [], "query": "te"}


class TestRankSuggestions:
    """Unit tests for the ranking helper behind the suggest ranking flag."""

    def test_sorts_by_ranking_score_when_present(self):
        hits = [
            {"title": "low", "_rankingScore": 0.2},
            {"title": "high", "_rankingScore": 0.9},
            {"title": "mid", "_rankingScore": 0.5},
        ]
        assert [h["title"] for h in _rank_suggestions(hits)] == ["high", "mid", "low"]

    def test_keeps_order_when_any_score_missing(self):
        hits = [{"title": "a", "_rankingScore": 0.1}, {"title": "b"}]
        assert _rank_suggestions(hits) == hits

    def test_keeps_order_for_plain_strings(self):
        assert _rank_suggestions(["Doc 1", "Doc 2"]) == ["Doc 1", "Doc 2"]

    def test_empty_input(self):
        assert _rank_suggestions([]) == []


class TestAdvancedSearchEndpoint:
    """Tests for POST /api/v1/search/advanced."""

    def test_advanced_search_with_filters(self, client, mock_meilisearch_client):
        """Advanced search with multiple filters."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }

        response = client.post(
            "/api/v1/search/advanced",
            json={
                "q": "report",
                "type": "document",
                "owner_id": "user-1",
                "tags": ["finance"],
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "page": 1,
                "size": 10,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "results" in data
        assert "total" in data

    def test_advanced_search_empty_body(self, client, mock_meilisearch_client):
        """Advanced search with empty body still works (match_all)."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }

        response = client.post("/api/v1/search/advanced", json={})
        assert response.status_code == 200


class TestAnalyticsEndpoint:
    """Tests for GET /api/v1/search/analytics."""

    def test_analytics_returns_data(self, client):
        """Analytics endpoint returns analytics data."""
        response = client.get("/api/v1/search/analytics")
        assert response.status_code == 200
        data = response.get_json()
        assert "popular_queries" in data
        assert "zero_result_queries" in data
        assert "total_searches" in data
        assert "avg_results_per_query" in data
