"""OpenSearch client for full-text search operations."""

from __future__ import annotations

import time
from typing import Any

import structlog
from opensearchpy import NotFoundError, OpenSearch

from app.config import OpenSearchConfig
from app.models.search_result import AnalyticsData, SearchHit, SearchResponse

logger = structlog.get_logger()

DOCUMENTS_INDEX = "otterworks-documents"
FILES_INDEX = "otterworks-files"

DOCUMENTS_INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "autocomplete_tokenizer",
                    "filter": ["lowercase"],
                },
                "autocomplete_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                },
            },
            "tokenizer": {
                "autocomplete_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 20,
                    "token_chars": ["letter", "digit"],
                }
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "keyword": {"type": "keyword"},
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                        "search_analyzer": "autocomplete_search_analyzer",
                    },
                },
            },
            "content": {"type": "text", "analyzer": "standard"},
            "type": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "suggest": {"type": "completion"},
        }
    },
}

FILES_INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "autocomplete_tokenizer",
                    "filter": ["lowercase"],
                },
                "autocomplete_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                },
            },
            "tokenizer": {
                "autocomplete_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 20,
                    "token_chars": ["letter", "digit"],
                }
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "keyword": {"type": "keyword"},
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                        "search_analyzer": "autocomplete_search_analyzer",
                    },
                },
            },
            "mime_type": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "folder_id": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "size": {"type": "long"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "suggest": {"type": "completion"},
        }
    },
}

# In-memory analytics store (would be Redis/DB in production)
_search_analytics: dict[str, Any] = {
    "queries": [],
    "total_searches": 0,
    "total_results": 0,
}

MAX_ANALYTICS_ENTRIES = 10000


def record_search_analytics(query: str, result_count: int) -> None:
    """Record a search query for analytics purposes."""
    _search_analytics["queries"].append(
        {"query": query, "result_count": result_count, "timestamp": time.time()}
    )
    _search_analytics["total_searches"] += 1
    _search_analytics["total_results"] += result_count
    # Prevent unbounded growth
    if len(_search_analytics["queries"]) > MAX_ANALYTICS_ENTRIES:
        _search_analytics["queries"] = _search_analytics["queries"][-MAX_ANALYTICS_ENTRIES:]


def get_search_analytics() -> AnalyticsData:
    """Compute search analytics from recorded queries."""
    queries = _search_analytics["queries"]
    total_searches = _search_analytics["total_searches"]

    # Popular queries: count occurrences
    query_counts: dict[str, int] = {}
    zero_result_counts: dict[str, int] = {}
    for entry in queries:
        q = entry["query"]
        query_counts[q] = query_counts.get(q, 0) + 1
        if entry["result_count"] == 0:
            zero_result_counts[q] = zero_result_counts.get(q, 0) + 1

    popular = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    zero_results = sorted(zero_result_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    avg_results = (
        _search_analytics["total_results"] / total_searches if total_searches > 0 else 0.0
    )

    return AnalyticsData(
        popular_queries=[{"query": q, "count": c} for q, c in popular],
        zero_result_queries=[{"query": q, "count": c} for q, c in zero_results],
        total_searches=total_searches,
        avg_results_per_query=round(avg_results, 2),
    )


class OpenSearchService:
    """Client for OpenSearch search and indexing operations."""

    def __init__(self, config: OpenSearchConfig) -> None:
        self.config = config
        self.client = OpenSearch(
            hosts=[config.url],
            use_ssl=config.use_ssl,
            verify_certs=config.verify_certs,
            timeout=config.request_timeout,
        )
        self.documents_index = config.documents_index
        self.files_index = config.files_index

    def ensure_indices(self) -> None:
        """Create indices if they don't exist."""
        if not self.client.indices.exists(self.documents_index):
            self.client.indices.create(self.documents_index, body=DOCUMENTS_INDEX_BODY)
            logger.info("opensearch_index_created", index=self.documents_index)
        if not self.client.indices.exists(self.files_index):
            self.client.indices.create(self.files_index, body=FILES_INDEX_BODY)
            logger.info("opensearch_index_created", index=self.files_index)

    def ping(self) -> bool:
        """Check if OpenSearch is reachable."""
        try:
            return bool(self.client.ping())
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
        indices = self._resolve_indices(doc_type)

        must_clauses: list[dict[str, Any]] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "name^3", "content", "tags^2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        filter_clauses: list[dict[str, Any]] = []
        if doc_type:
            filter_clauses.append({"term": {"type": doc_type}})
        if owner_id:
            filter_clauses.append({"term": {"owner_id": owner_id}})

        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "highlight": {
                "fields": {
                    "title": {},
                    "name": {},
                    "content": {"fragment_size": 200, "number_of_fragments": 3},
                }
            },
            "sort": ["_score", {"updated_at": {"order": "desc", "unmapped_type": "date"}}],
        }

        response = self.client.search(index=",".join(indices), body=body)

        hits = self._parse_hits(response)
        total = response["hits"]["total"]["value"]

        record_search_analytics(query, total)

        return SearchResponse(
            results=hits,
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
        indices = self._resolve_indices(doc_type)

        must_clauses: list[dict[str, Any]] = []
        if query:
            must_clauses.append(
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "name^3", "content", "tags^2"],
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                    }
                }
            )

        filter_clauses: list[dict[str, Any]] = []
        if doc_type:
            filter_clauses.append({"term": {"type": doc_type}})
        if owner_id:
            filter_clauses.append({"term": {"owner_id": owner_id}})
        if tags:
            filter_clauses.append({"terms": {"tags": tags}})
        if date_from or date_to:
            date_range: dict[str, str] = {}
            if date_from:
                date_range["gte"] = date_from
            if date_to:
                date_range["lte"] = date_to
            filter_clauses.append({"range": {"created_at": date_range}})

        bool_query: dict[str, Any] = {"filter": filter_clauses}
        if must_clauses:
            bool_query["must"] = must_clauses
        else:
            bool_query["must"] = [{"match_all": {}}]

        body: dict[str, Any] = {
            "query": {"bool": bool_query},
            "from": (page - 1) * page_size,
            "size": page_size,
            "highlight": {
                "fields": {
                    "title": {},
                    "name": {},
                    "content": {"fragment_size": 200, "number_of_fragments": 3},
                }
            },
            "sort": ["_score", {"updated_at": {"order": "desc", "unmapped_type": "date"}}],
        }

        response = self.client.search(index=",".join(indices), body=body)

        hits = self._parse_hits(response)
        total = response["hits"]["total"]["value"]

        search_term = query or "*"
        record_search_analytics(search_term, total)

        return SearchResponse(
            results=hits,
            total=total,
            page=page,
            page_size=page_size,
            query=search_term,
        )

    def suggest(self, prefix: str, size: int = 10) -> list[str]:
        """Autocomplete suggestions using edge_ngram on title/name fields."""
        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title.autocomplete": {"query": prefix}}},
                        {"match": {"name.autocomplete": {"query": prefix}}},
                    ]
                }
            },
            "size": size,
            "_source": ["title", "name"],
        }

        indices = f"{self.documents_index},{self.files_index}"
        response = self.client.search(index=indices, body=body)

        suggestions: list[str] = []
        seen: set[str] = set()
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            text = source.get("title") or source.get("name", "")
            if text and text not in seen:
                suggestions.append(text)
                seen.add(text)
        return suggestions

    def index_document(self, document: dict[str, Any]) -> None:
        """Index or update a document in the documents index."""
        doc_id = document.get("id", "")
        title = document.get("title", "")
        doc = {**document, "type": "document"}
        doc["suggest"] = {"input": title.split()} if title else {"input": []}
        self.client.index(index=self.documents_index, id=doc_id, body=doc, refresh="wait_for")
        logger.info("document_indexed", document_id=doc_id, index=self.documents_index)

    def index_file(self, file_data: dict[str, Any]) -> None:
        """Index or update a file in the files index."""
        file_id = file_data.get("id", "")
        name = file_data.get("name", "")
        doc = {**file_data, "type": "file"}
        doc["suggest"] = {"input": name.split()} if name else {"input": []}
        self.client.index(index=self.files_index, id=file_id, body=doc, refresh="wait_for")
        logger.info("file_indexed", file_id=file_id, index=self.files_index)

    def delete_document(self, doc_type: str, doc_id: str) -> bool:
        """Remove a document or file from the index."""
        index = self.documents_index if doc_type == "document" else self.files_index
        try:
            self.client.delete(index=index, id=doc_id, refresh="wait_for")
            logger.info("document_removed_from_index", doc_id=doc_id, index=index)
            return True
        except NotFoundError:
            logger.warning("document_not_found_in_index", doc_id=doc_id, index=index)
            return False

    def reindex(self) -> dict[str, Any]:
        """Delete and recreate indices (admin operation)."""
        for index_name, index_body in [
            (self.documents_index, DOCUMENTS_INDEX_BODY),
            (self.files_index, FILES_INDEX_BODY),
        ]:
            if self.client.indices.exists(index_name):
                self.client.indices.delete(index_name)
                logger.info("opensearch_index_deleted", index=index_name)
            self.client.indices.create(index_name, body=index_body)
            logger.info("opensearch_index_created", index=index_name)

        return {"status": "reindex_complete", "indices": [self.documents_index, self.files_index]}

    def _resolve_indices(self, doc_type: str | None) -> list[str]:
        """Determine which indices to search based on doc_type."""
        if doc_type == "document":
            return [self.documents_index]
        if doc_type == "file":
            return [self.files_index]
        return [self.documents_index, self.files_index]

    def _parse_hits(self, response: dict[str, Any]) -> list[SearchHit]:
        """Parse OpenSearch response hits into SearchHit models."""
        hits: list[SearchHit] = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            title = source.get("title") or source.get("name", "")
            content_snippet = ""
            highlights = hit.get("highlight", {})
            if "content" in highlights:
                content_snippet = " ... ".join(highlights["content"])
            elif "content" in source:
                content_snippet = source["content"][:200]

            hits.append(
                SearchHit(
                    id=source.get("id", hit["_id"]),
                    title=title,
                    content_snippet=content_snippet,
                    type=source.get("type", "unknown"),
                    owner_id=source.get("owner_id", ""),
                    tags=source.get("tags", []),
                    score=hit.get("_score", 0.0),
                    highlights=highlights,
                    created_at=source.get("created_at"),
                    updated_at=source.get("updated_at"),
                    mime_type=source.get("mime_type"),
                    folder_id=source.get("folder_id"),
                    size=source.get("size"),
                )
            )
        return hits
