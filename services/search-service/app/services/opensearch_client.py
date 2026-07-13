"""Amazon OpenSearch Serverless client for full-text search operations."""

from __future__ import annotations

from typing import Any

import boto3
import structlog
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import NotFoundError
from opensearchpy.helpers import bulk

from app.config import OpenSearchConfig
from app.models.search_result import SearchHit, SearchResponse
from app.services.meilisearch_client import record_search_analytics

logger = structlog.get_logger()


class OpenSearchService:
    """Client for Amazon OpenSearch Serverless search and indexing operations."""

    def __init__(self, config: OpenSearchConfig) -> None:
        self.config = config
        host = config.endpoint.replace("https://", "").replace("http://", "")
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, config.region, "aoss")
        self.client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20,
            timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
        self.documents_index_name = config.documents_index
        self.files_index_name = config.files_index

    def ensure_indices(self) -> None:
        """Create the document and file indices if they do not exist."""
        mappings = {
            self.documents_index_name: {
                "properties": {
                    "title": {"type": "text", "fields": {"sayt": {"type": "search_as_you_type"}}},
                    "content": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "owner_id": {"type": "keyword"},
                    "created_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis",
                    },
                    "updated_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis",
                    },
                }
            },
            self.files_index_name: {
                "properties": {
                    "name": {"type": "text", "fields": {"sayt": {"type": "search_as_you_type"}}},
                    "tags": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "owner_id": {"type": "keyword"},
                    "mime_type": {"type": "keyword"},
                    "folder_id": {"type": "keyword"},
                    "size": {"type": "long"},
                    "created_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis",
                    },
                    "updated_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis",
                    },
                }
            },
        }
        for index_name, mapping in mappings.items():
            if not self.client.indices.exists(index_name):
                self.client.indices.create(index_name, body={"mappings": mapping})
                logger.info("opensearch_index_created", index=index_name)

    def ping(self) -> bool:
        """Check whether OpenSearch is reachable.

        Uses an index existence check rather than the root info API, which
        Amazon OpenSearch Serverless does not expose. Reachability is what
        matters here, so a missing index still counts as reachable.
        """
        try:
            self.client.indices.exists(self.documents_index_name)
            return True
        except Exception:
            return False

    def _resolve_indices(self, doc_type: str | None) -> list[str]:
        """Determine which indices to search based on type filter."""
        if doc_type == "document":
            return [self.documents_index_name]
        if doc_type == "file":
            return [self.files_index_name]
        return [self.documents_index_name, self.files_index_name]

    @staticmethod
    def _total(response: dict[str, Any]) -> int:
        total = response.get("hits", {}).get("total", 0)
        return int(total.get("value", 0) if isinstance(total, dict) else total)

    def _search(
        self,
        query: str | None,
        doc_type: str | None,
        owner_id: str | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        page: int,
        page_size: int,
    ) -> SearchResponse:
        filters: list[dict[str, Any]] = []
        if doc_type:
            filters.append({"term": {"type": doc_type}})
        if owner_id:
            filters.append({"term": {"owner_id": owner_id}})
        if tags:
            filters.append({"bool": {"should": [{"term": {"tags": tag}} for tag in tags], "minimum_should_match": 1}})
        if date_from or date_to:
            range_query: dict[str, str] = {}
            if date_from:
                range_query["gte"] = date_from
            if date_to:
                range_query["lte"] = date_to
            filters.append({"range": {"created_at": range_query}})

        search_term = query or ""
        must = [{"match_all": {}}] if not search_term else [
            {
                "multi_match": {
                    "query": search_term,
                    "fields": ["title^2", "content", "tags", "name^2", "mime_type"],
                    "type": "best_fields",
                }
            }
        ]
        body = {
            "query": {"bool": {"must": must, "filter": filters}},
            "from": (page - 1) * page_size,
            "size": page_size,
            "highlight": {
                "fields": {"title": {}, "name": {}, "content": {}},
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            },
        }
        response = self.client.search(index=",".join(self._resolve_indices(doc_type)), body=body)
        total = self._total(response)
        results = [
            self._parse_hit(
                hit.get("_source", {}),
                hit.get("_index", ""),
                hit.get("highlight", {}),
                hit.get("_score"),
                hit.get("_id", ""),
            )
            for hit in response.get("hits", {}).get("hits", [])
        ]
        return SearchResponse(results, total, page, page_size, search_term or "*")

    def search(
        self,
        query: str,
        doc_type: str | None = None,
        owner_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """Full-text search across documents and files."""
        result = self._search(query, doc_type, owner_id, None, None, None, page, page_size)
        record_search_analytics(query, result.total)
        return result

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
        result = self._search(query, doc_type, owner_id, tags, date_from, date_to, page, page_size)
        record_search_analytics(query or "*", result.total)
        return result

    def suggest(self, prefix: str, size: int = 10) -> list[str]:
        """Use bool_prefix because match does not provide type-ahead behavior."""
        suggestions: list[str] = []
        seen: set[str] = set()
        for index_name, field in (
            (self.documents_index_name, "title"),
            (self.files_index_name, "name"),
        ):
            response = self.client.search(
                index=index_name,
                body={
                    "query": {
                        "multi_match": {
                            "query": prefix,
                            "type": "bool_prefix",
                            "fields": [f"{field}.sayt", f"{field}.sayt._2gram", f"{field}.sayt._3gram"],
                        }
                    },
                    "_source": [field],
                    "size": size,
                },
            )
            for hit in response.get("hits", {}).get("hits", []):
                text = hit.get("_source", {}).get(field, "")
                if text and text not in seen:
                    suggestions.append(text)
                    seen.add(text)
                    if len(suggestions) >= size:
                        return suggestions
        return suggestions

    def index_document(self, document: dict[str, Any]) -> None:
        """Index or update a document."""
        doc = {**document, "type": "document"}
        self.client.index(index=self.documents_index_name, id=doc["id"], body=doc)
        logger.info("document_indexed", document_id=doc.get("id"))

    def index_file(self, file_data: dict[str, Any]) -> None:
        """Index or update a file."""
        doc = {**file_data, "type": "file"}
        self.client.index(index=self.files_index_name, id=doc["id"], body=doc)
        logger.info("file_indexed", file_id=doc.get("id"))

    def delete_document(self, doc_type: str, doc_id: str) -> bool:
        """Remove a document or file from the index."""
        index_name = self.documents_index_name if doc_type == "document" else self.files_index_name
        try:
            self.client.get(index=index_name, id=doc_id)
        except NotFoundError:
            logger.warning("document_not_found_in_index", doc_id=doc_id, index=index_name)
            return False
        self.client.delete(index=index_name, id=doc_id)
        logger.info("document_removed_from_index", doc_id=doc_id, index=index_name)
        return True

    def reindex(
        self,
        documents: list[dict[str, Any]] | None = None,
        files: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Recreate both indices and optionally bulk-index supplied data."""
        for index_name in [self.documents_index_name, self.files_index_name]:
            try:
                if self.client.indices.exists(index_name):
                    self.client.indices.delete(index_name)
            except NotFoundError:
                pass
        self.ensure_indices()
        documents = documents or []
        files = files or []
        actions = [
            {"_index": self.documents_index_name, "_id": doc["id"], "_source": {**doc, "type": "document"}}
            for doc in documents
        ] + [
            {"_index": self.files_index_name, "_id": file_data["id"], "_source": {**file_data, "type": "file"}}
            for file_data in files
        ]
        if actions:
            bulk(self.client, actions)
        return {
            "status": "reindexed",
            "indices": [self.documents_index_name, self.files_index_name],
            "indexed_counts": {"documents": len(documents), "files": len(files)},
        }

    def _parse_hit(
        self,
        source: dict[str, Any],
        index_name: str,
        highlight: dict[str, Any],
        score: float | None,
        hit_id: str = "",
    ) -> SearchHit:
        """Convert an OpenSearch hit to a SearchHit model."""
        is_doc = index_name == self.documents_index_name
        title_field = "title" if is_doc else "name"
        highlights: dict[str, list[str]] = {}
        for field, values in highlight.items():
            formatted = values if isinstance(values, list) else [values]
            if any("<em>" in str(value) for value in formatted):
                highlights[field] = [str(value) for value in formatted]
        content = highlight.get("content", [source.get("content", "")])
        content_snippet = str(content[0] if isinstance(content, list) else content)[:200] if is_doc else ""
        return SearchHit(
            id=source.get("id", hit_id),
            title=source.get(title_field, ""),
            content_snippet=content_snippet,
            type=source.get("type", "document" if is_doc else "file"),
            owner_id=source.get("owner_id", ""),
            tags=source.get("tags", []),
            score=float(score or 0.0),
            highlights=highlights,
            created_at=source.get("created_at"),
            updated_at=source.get("updated_at"),
            mime_type=source.get("mime_type"),
            folder_id=source.get("folder_id"),
            size=source.get("size"),
        )
