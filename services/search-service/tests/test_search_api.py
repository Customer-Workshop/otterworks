"""Tests for search API endpoints."""

from __future__ import annotations

from unittest.mock import patch


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

    def test_suggest_ranked_orders_by_ranking_score(self, client, mock_meilisearch_client):
        """Ranked suggest requests _rankingScore and sorts by it."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 2,
            "hits": [
                {"title": "Low", "_rankingScore": 0.2},
                {"title": "High", "_rankingScore": 0.9},
            ],
        }

        with patch("app.api.search._chaos_active", return_value=True):
            response = client.get("/api/v1/search/suggest?q=te")

        assert response.status_code == 200
        assert response.get_json()["suggestions"] == ["High", "Low"]
        _, params = mock_index.search.call_args[0]
        assert params["showRankingScore"] is True

    def test_suggest_ranked_tolerates_missing_score(self, client, mock_meilisearch_client):
        """Ranked suggest does not 500 when hits lack _rankingScore."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.return_value = {
            "estimatedTotalHits": 2,
            "hits": [
                {"title": "Unscored"},
                {"title": "Scored", "_rankingScore": 0.5},
            ],
        }

        with patch("app.api.search._chaos_active", return_value=True):
            response = client.get("/api/v1/search/suggest?q=te")

        assert response.status_code == 200
        assert response.get_json()["suggestions"] == ["Scored", "Unscored"]

    def test_suggest_ranked_merges_both_indexes(self, client, mock_meilisearch_client):
        """Ranked suggest ranks files against documents and keeps the best duplicate score."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.search.side_effect = [
            {"hits": [{"title": f"Doc {i}", "_rankingScore": 0.3} for i in range(10)]},
            {"hits": [{"name": "Top File", "_rankingScore": 0.95}, {"name": "Doc 0", "_rankingScore": 0.9}]},
        ]

        with patch("app.api.search._chaos_active", return_value=True):
            response = client.get("/api/v1/search/suggest?q=te")

        assert response.status_code == 200
        suggestions = response.get_json()["suggestions"]
        assert suggestions[:2] == ["Top File", "Doc 0"]
        assert len(suggestions) == 10
        assert mock_index.search.call_count == 2

    def test_suggest_ranked_empty_index(self, client, mock_meilisearch_client):
        """Ranked suggest on an empty index returns 200 with no suggestions."""
        with patch("app.api.search._chaos_active", return_value=True):
            response = client.get("/api/v1/search/suggest?q=te")

        assert response.status_code == 200
        assert response.get_json()["suggestions"] == []


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
