"""Tests for MeiliSearch client analytics and utility functions."""

from __future__ import annotations

import threading

from app.services.meilisearch_client import (
    _search_analytics,
    get_search_analytics,
    record_search_analytics,
)


def _reset_analytics():
    """Reset the module-level analytics state between tests."""
    with threading.Lock():
        _search_analytics["queries"] = []
        _search_analytics["total_searches"] = 0
        _search_analytics["total_results"] = 0


class TestRecordSearchAnalytics:
    def setup_method(self):
        _reset_analytics()

    def test_records_single_query(self):
        record_search_analytics("hello", 5)
        analytics = get_search_analytics()
        assert analytics.total_searches == 1
        assert analytics.avg_results_per_query == 5.0

    def test_records_multiple_queries(self):
        record_search_analytics("hello", 5)
        record_search_analytics("world", 3)
        record_search_analytics("hello", 2)

        analytics = get_search_analytics()
        assert analytics.total_searches == 3
        assert analytics.avg_results_per_query == round(10 / 3, 2)

    def test_popular_queries_sorted_by_count(self):
        for _ in range(5):
            record_search_analytics("popular", 1)
        for _ in range(2):
            record_search_analytics("less popular", 1)

        analytics = get_search_analytics()
        assert len(analytics.popular_queries) >= 2
        assert analytics.popular_queries[0]["query"] == "popular"
        assert analytics.popular_queries[0]["count"] == 5

    def test_zero_result_queries(self):
        record_search_analytics("no results", 0)
        record_search_analytics("has results", 5)
        record_search_analytics("no results", 0)

        analytics = get_search_analytics()
        assert len(analytics.zero_result_queries) >= 1
        zero_q = next(q for q in analytics.zero_result_queries if q["query"] == "no results")
        assert zero_q["count"] == 2

    def test_empty_analytics(self):
        analytics = get_search_analytics()
        assert analytics.total_searches == 0
        assert analytics.avg_results_per_query == 0.0
        assert analytics.popular_queries == []
        assert analytics.zero_result_queries == []


class TestMeiliSearchServiceEscape:
    def test_escape_quotes(self):
        from app.services.meilisearch_client import MeiliSearchService

        assert MeiliSearchService._escape('he said "hello"') == 'he said \\"hello\\"'

    def test_escape_backslash(self):
        from app.services.meilisearch_client import MeiliSearchService

        assert MeiliSearchService._escape("path\\to\\file") == "path\\\\to\\\\file"

    def test_escape_clean_string(self):
        from app.services.meilisearch_client import MeiliSearchService

        assert MeiliSearchService._escape("hello world") == "hello world"
