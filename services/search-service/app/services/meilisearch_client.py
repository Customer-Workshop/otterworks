"""MeiliSearch client for full-text search operations."""

from __future__ import annotations

import threading
import time
from typing import Any

import meilisearch
import structlog

from app.config import MeiliSearchConfig
from app.models.search_result import AnalyticsData, SearchHit, SearchResponse

logger = structlog.get_logger()

FILES_INDEX = "files"
DOCUMENTS_INDEX = "documents"

# In-memory analytics store
_analytics_lock = threading.Lock()
_search_analytics: dict[str, Any] = {
    "queries": [],
    "total_searches": 0,
    "total_results": 0,
}

MAX_ANALYTICS_ENTRIES = 10000


def record_search_analytics(query: str, result_count: int) -> None:
    """Record a search query for analytics purposes."""
    with _analytics_lock:
        _search_analytics["queries"].append(
            {"query": query, "result_count": result_count, "timestamp": time.time()}
        )
        _search_analytics["total_searches"] += 1
        _search_analytics["total_results"] += result_count
        if len(_search_analytics["queries"]) > MAX_ANALYTICS_ENTRIES:
            _search_analytics["queries"] = _search_analytics["queries"][-MAX_ANALYTICS_ENTRIES:]


def get_search_analytics() -> AnalyticsData:
    """Compute search analytics from recorded queries."""
    with _analytics_lock:
        queries = list(_search_analytics["queries"])
        total_searches = _search_analytics["total_searches"]
        total_results = _search_analytics["total_results"]

    query_counts: dict[str, int] = {}
    zero_result_counts: dict[str, int] = {}
    for entry in queries:
        q = entry["query"]
        query_counts[q] = query_counts.get(q, 0) + 1
        if entry["result_count"] == 0:
            zero_result_counts[q] = zero_result_counts.get(q, 0) + 1

    popular = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    zero_results = sorted(zero_result_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    avg_results = total_results / total_searches if total_searches > 0 else 0.0

    return AnalyticsData(
        popular_queries=[{"query": q, "count": c} for q, c in popular],
        zero_result_queries=[{"query": q, "count": c} for q, c in zero_results],
        total_searches=total_searches,
        avg_results_per_query=round(avg_results, 2),
    )


class MeiliSearchService:
    """Client for MeiliSearch search and indexing operations."""

    def __init__(self, config: MeiliSearchConfig) -> None:
        self.config = config
        self.client = meilisearch.Client(config.url, config.api_key or None)
        self.documents_index_name = config.documents_index
        self.files_index_name = config.files_index

    def ensure_indices(self) -> None:
        """Create indices and configure settings if they don't exist."""
        for index_name in [self.documents_index_name, self.files_index_name]:
            try:
                self.client.get_index(index_name)
            except meilisearch.errors.MeilisearchApiError:
                task = self.client.create_index(index_name, {"primaryKey": "id"})
                self.client.wait_for_task(task.task_uid, timeout_in_ms=30000)
                logger.info("meilisearch_index_created", index=index_name)

        # Configure documents index
        docs_index = self.client.index(self.documents_index_name)
        docs_index.update_searchable_attributes(["title", "content", "tags"])
        docs_index.update_filterable_attributes(["type", "owner_id", "tags", "created_at", "updated_at"])
        docs_index.update_sortable_attributes(["updated_at", "created_at"])
        docs_index.update_ranking_rules([
            "words", "typo", "proximity", "attribute", "sort", "exactness",
        ])

        # Configure files index
        files_index = self.client.index(self.files_index_name)
        files_index.update_searchable_attributes(["name", "tags", "mime_type"])
        files_index.update_filterable_attributes(["type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at"])
        files_index.update_sortable_attributes(["updated_at", "created_at", "size"])
        files_index.update_ranking_rules([
            "words", "typo", "proximity", "attribute", "sort", "exactness",
        ])

        logger.info("meilisearch_indices_configured")

    def ping(self) -> bool:
        """Check if MeiliSearch is reachable."""
        try:
            self.client.health()
            return True
        except Exception:
            return False

    def search(
        self,
        query: str,
        doc_type: str | None = None,
        owner_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """Full-text search across documents and files."""
        filter_parts: list[str] = []
        if doc_type:
            filter_parts.append(f'type = "{doc_type}"')
        if owner_id:
            filter_parts.append(f'owner_id = "{owner_id}"')

        search_params: dict[str, Any] = {
            "offset": (page - 1) * page_size,
            "limit": page_size,
            "attributesToHighlight": ["title", "name", "content"],
            "highlightPreTag": "<em>",
            "highlightPostTag": "</em>",
            "attributesToCrop": ["content"],
            "cropLength": 200,
        }
        if filter_parts:
            search_params["filter"] = " AND ".join(filter_parts)

        indices_to_search = self._resolve_indices(doc_type)
        all_hits: list[SearchHit] = []
        total = 0

        for index_name in indices_to_search:
            index = self.client.index(index_name)
            result = index.search(query, search_params)
            total += result["estimatedTotalHits"]
            for hit in result["hits"]:
                all_hits.append(self._parse_hit(hit, index_name))

        # Sort by relevance (MeiliSearch returns pre-sorted within each index)
        # For multi-index, interleave by keeping original order
        record_search_analytics(query, total)

        return SearchResponse(
            results=all_hits[:page_size],
            total=total,
            page=page,
            page_size=page_size,
            query=query,
        )

    def advanced_search(
        self,
        query: str | None = None,
        doc_type: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """Advanced search with detailed filters."""
        filter_parts: list[str] = []
        if doc_type:
            filter_parts.append(f'type = "{doc_type}"')
        if owner_id:
            filter_parts.append(f'owner_id = "{owner_id}"')
        if tags:
            tag_filters = [f'tags = "{tag}"' for tag in tags]
            filter_parts.append(f'({" OR ".join(tag_filters)})')
        if date_from:
            filter_parts.append(f'created_at >= "{date_from}"')
        if date_to:
            filter_parts.append(f'created_at <= "{date_to}"')

        search_params: dict[str, Any] = {
            "offset": (page - 1) * page_size,
            "limit": page_size,
            "attributesToHighlight": ["title", "name", "content"],
            "highlightPreTag": "<em>",
            "highlightPostTag": "</em>",
            "attributesToCrop": ["content"],
            "cropLength": 200,
        }
        if filter_parts:
            search_params["filter"] = " AND ".join(filter_parts)

        search_term = query or ""
        indices_to_search = self._resolve_indices(doc_type)
        all_hits: list[SearchHit] = []
        total = 0

        for index_name in indices_to_search:
            index = self.client.index(index_name)
            result = index.search(search_term, search_params)
            total += result["estimatedTotalHits"]
            for hit in result["hits"]:
                all_hits.append(self._parse_hit(hit, index_name))

        record_search_analytics(search_term or "*", total)

        return SearchResponse(
            results=all_hits[:page_size],
            total=total,
            page=page,
            page_size=page_size,
            query=search_term or "*",
        )

    def suggest(self, prefix: str, size: int = 10) -> list[str]:
        """Autocomplete suggestions using MeiliSearch prefix matching."""
        suggestions: list[str] = []
        seen: set[str] = set()

        for index_name in [self.documents_index_name, self.files_index_name]:
            index = self.client.index(index_name)
            result = index.search(prefix, {
                "limit": size,
                "attributesToRetrieve": ["title", "name"],
            })
            for hit in result["hits"]:
                text = hit.get("title") or hit.get("name", "")
                if text and text not in seen:
                    suggestions.append(text)
                    seen.add(text)
                    if len(suggestions) >= size:
                        break
            if len(suggestions) >= size:
                break

        return suggestions

    def index_document(self, document: dict[str, Any]) -> None:
        """Index or update a document."""
        doc = {**document, "type": "document"}
        index = self.client.index(self.documents_index_name)
        task = index.add_documents([doc])
        self.client.wait_for_task(task.task_uid, timeout_in_ms=10000)
        logger.info("document_indexed", document_id=doc.get("id"))

    def index_file(self, file_data: dict[str, Any]) -> None:
        """Index or update a file."""
        doc = {**file_data, "type": "file"}
        index = self.client.index(self.files_index_name)
        task = index.add_documents([doc])
        self.client.wait_for_task(task.task_uid, timeout_in_ms=10000)
        logger.info("file_indexed", file_id=doc.get("id"))

    def delete_document(self, doc_type: str, doc_id: str) -> bool:
        """Remove a document or file from the index."""
        index_name = self.documents_index_name if doc_type == "document" else self.files_index_name
        index = self.client.index(index_name)
        try:
            task = index.delete_document(doc_id)
            self.client.wait_for_task(task.task_uid, timeout_in_ms=10000)
            logger.info("document_removed_from_index", doc_id=doc_id, index=index_name)
            return True
        except meilisearch.errors.MeilisearchApiError:
            logger.warning("document_not_found_in_index", doc_id=doc_id, index=index_name)
            return False

    def reindex(self) -> dict[str, Any]:
        """Delete and recreate indices."""
        for index_name in [self.documents_index_name, self.files_index_name]:
            try:
                task = self.client.delete_index(index_name)
                self.client.wait_for_task(task.task_uid, timeout_in_ms=30000)
                logger.info("meilisearch_index_deleted", index=index_name)
            except meilisearch.errors.MeilisearchApiError:
                pass
        self.ensure_indices()
        return {"status": "reindexed", "indices": [self.documents_index_name, self.files_index_name]}

    def _resolve_indices(self, doc_type: str | None) -> list[str]:
        """Determine which indices to search based on type filter."""
        if doc_type == "document":
            return [self.documents_index_name]
        if doc_type == "file":
            return [self.files_index_name]
        return [self.documents_index_name, self.files_index_name]

    def _parse_hit(self, hit: dict[str, Any], index_name: str) -> SearchHit:
        """Convert a MeiliSearch hit to a SearchHit model."""
        formatted = hit.get("_formatted", {})
        highlights: dict[str, list[str]] = {}
        for field in ["title", "name", "content"]:
            if field in formatted and "<em>" in str(formatted[field]):
                highlights[field] = [str(formatted[field])]

        is_doc = index_name == self.documents_index_name
        return SearchHit(
            id=hit.get("id", ""),
            title=hit.get("title", "") if is_doc else hit.get("name", ""),
            content_snippet=str(formatted.get("content", ""))[:200] if is_doc else "",
            type=hit.get("type", "document" if is_doc else "file"),
            owner_id=hit.get("owner_id", ""),
            tags=hit.get("tags", []),
            score=0.0,
            highlights=highlights,
            created_at=hit.get("created_at"),
            updated_at=hit.get("updated_at"),
            mime_type=hit.get("mime_type"),
            folder_id=hit.get("folder_id"),
            size=hit.get("size"),
        )
