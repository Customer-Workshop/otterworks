"""Amazon OpenSearch (Serverless / managed) client for full-text search.

Sibling adapter to :mod:`app.services.meilisearch_client`. It implements the
SAME public interface (``ensure_indices`` / ``ping`` / ``search`` /
``advanced_search`` / ``suggest`` / ``index_document`` / ``index_file`` /
``delete_document`` / ``reindex``) so the backend-agnostic API layer can talk to
either backend unchanged, selected by the ``SEARCH_BACKEND`` env flag.

The self-managed MeiliSearch path stays the default on ``main``; this adapter is
the managed/serverless target proven behavior-identical by the repo's contract
and API-flow suites.

Behavioral parity note — the ``/suggest`` type-ahead:
MeiliSearch is prefix-first out of the box, so a naive OpenSearch ``match``
query would break type-ahead (``match`` tokenizes and matches whole terms, not
prefixes). To hold parity we map the suggest path to ``search_as_you_type`` /
``match_phrase_prefix`` (see :meth:`OpenSearchService.suggest`).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import structlog
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import NotFoundError, OpenSearchException

from app.config import OpenSearchConfig
from app.models.search_result import SearchHit, SearchResponse

# Shared, backend-agnostic analytics store (same functions the MeiliSearch path
# and the API layer use) so switching backends does not change analytics.
from app.services.meilisearch_client import record_search_analytics

logger = structlog.get_logger()

FILES_INDEX = "files"
DOCUMENTS_INDEX = "documents"

# Fields searched for full-text relevance, mirroring the MeiliSearch searchable
# attributes (documents: title/content/tags; files: name/tags/mime_type).
_DOC_SEARCH_FIELDS = ["title^2", "content", "tags"]
_FILE_SEARCH_FIELDS = ["name^2", "tags", "mime_type"]
_HIGHLIGHT_FIELDS = ["title", "name", "content"]


def _documents_mapping() -> dict[str, Any]:
    """Index mapping for documents (mirrors MeiliSearch searchable/filterable)."""
    return {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "title": {
                    "type": "text",
                    # search_as_you_type powers prefix-first type-ahead so the
                    # /suggest contract holds against OpenSearch.
                    "fields": {"sayt": {"type": "search_as_you_type"}},
                },
                "content": {"type": "text"},
                "tags": {"type": "keyword"},
                "type": {"type": "keyword"},
                "owner_id": {"type": "keyword"},
                # ISO-8601 strings; keyword keeps range filters robust to nulls
                # and mixed date/datetime granularity while sorting correctly.
                "created_at": {"type": "keyword"},
                "updated_at": {"type": "keyword"},
            }
        }
    }


def _files_mapping() -> dict[str, Any]:
    """Index mapping for files (mirrors MeiliSearch searchable/filterable)."""
    return {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "fields": {"sayt": {"type": "search_as_you_type"}},
                },
                "tags": {"type": "keyword"},
                "mime_type": {"type": "keyword"},
                "type": {"type": "keyword"},
                "owner_id": {"type": "keyword"},
                "folder_id": {"type": "keyword"},
                "size": {"type": "long"},
                "created_at": {"type": "keyword"},
                "updated_at": {"type": "keyword"},
            }
        }
    }


class OpenSearchService:
    """Client for Amazon OpenSearch search and indexing operations."""

    def __init__(self, config: OpenSearchConfig) -> None:
        self.config = config
        self.documents_index_name = config.documents_index
        self.files_index_name = config.files_index
        self.serverless = config.serverless
        self.client = self._build_client(config)

    @staticmethod
    def _build_client(config: OpenSearchConfig) -> OpenSearch:
        """Construct an OpenSearch client for Serverless (SigV4) or a node."""
        parsed = urlparse(config.endpoint)
        host = parsed.hostname or config.endpoint
        use_ssl = parsed.scheme == "https"
        port = parsed.port or (443 if use_ssl else 9200)

        common: dict[str, Any] = {
            "hosts": [{"host": host, "port": port}],
            "use_ssl": use_ssl,
            "verify_certs": use_ssl,
            "connection_class": RequestsHttpConnection,
            "pool_maxsize": 20,
            "timeout": 30,
        }

        if config.serverless:
            # Amazon OpenSearch Serverless: sign requests with SigV4 (service
            # "aoss") using the pod's IRSA credentials.
            from boto3 import Session
            from requests_aws4auth import AWS4Auth

            creds = Session().get_credentials()
            awsauth = AWS4Auth(
                creds.access_key,
                creds.secret_key,
                config.region,
                "aoss",
                session_token=creds.token,
            )
            return OpenSearch(http_auth=awsauth, **common)

        http_auth = (
            (config.username, config.password)
            if config.username and config.password
            else None
        )
        return OpenSearch(http_auth=http_auth, **common)

    # --- schema management -------------------------------------------------

    def ensure_indices(self) -> None:
        """Create indices with mappings if they do not exist."""
        for index_name, body in (
            (self.documents_index_name, _documents_mapping()),
            (self.files_index_name, _files_mapping()),
        ):
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(index=index_name, body=body)
                logger.info("opensearch_index_created", index=index_name)
        logger.info("opensearch_indices_configured")

    def ping(self) -> bool:
        """Check if the OpenSearch endpoint is reachable."""
        try:
            # OpenSearch Serverless does not expose the root/ping API; probe an
            # index instead. A cluster node answers ping() directly.
            if self.serverless:
                return bool(self.client.indices.exists(index=self.documents_index_name))
            return bool(self.client.ping())
        except Exception:
            return False

    # --- query -------------------------------------------------------------

    def _build_filters(
        self,
        doc_type: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build the OpenSearch bool-filter clauses (exact/range, non-scoring)."""
        filters: list[dict[str, Any]] = []
        if doc_type:
            filters.append({"term": {"type": doc_type}})
        if owner_id:
            filters.append({"term": {"owner_id": owner_id}})
        if tags:
            filters.append({"terms": {"tags": tags}})
        if date_from or date_to:
            date_range: dict[str, str] = {}
            if date_from:
                date_range["gte"] = date_from
            if date_to:
                date_range["lte"] = date_to
            filters.append({"range": {"created_at": date_range}})
        return filters

    def _resolve_indices(self, doc_type: str | None) -> list[str]:
        """Determine which indices to search based on the type filter."""
        if doc_type == "document":
            return [self.documents_index_name]
        if doc_type == "file":
            return [self.files_index_name]
        return [self.documents_index_name, self.files_index_name]

    def _run_search(
        self,
        query: str,
        indices: list[str],
        filters: list[dict[str, Any]],
        page: int,
        page_size: int,
    ) -> SearchResponse:
        """Execute a paginated multi-index search and assemble a SearchResponse."""
        all_hits: list[SearchHit] = []
        total = 0
        multi_index = len(indices) > 1
        # For a single index, page natively; across indices, fetch the first
        # ``page * page_size`` from each then slice (mirrors the MeiliSearch path).
        per_index_size = page * page_size if multi_index else page_size
        offset = 0 if multi_index else (page - 1) * page_size

        for index_name in indices:
            fields = (
                _DOC_SEARCH_FIELDS
                if index_name == self.documents_index_name
                else _FILE_SEARCH_FIELDS
            )
            if query:
                must: dict[str, Any] = {
                    "multi_match": {
                        "query": query,
                        "fields": fields,
                        "fuzziness": "AUTO",
                        "type": "best_fields",
                    }
                }
            else:
                must = {"match_all": {}}

            body: dict[str, Any] = {
                "from": offset,
                "size": per_index_size,
                "query": {"bool": {"must": [must], "filter": filters}},
                "highlight": {
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"],
                    "fields": {f: {} for f in _HIGHLIGHT_FIELDS},
                },
            }

            try:
                result = self.client.search(index=index_name, body=body)
            except OpenSearchException as exc:
                logger.warning("search_query_error", index=index_name, error=str(exc))
                raise ValueError(f"Invalid search query: {exc}") from exc

            total += result["hits"]["total"]["value"]
            for hit in result["hits"]["hits"]:
                all_hits.append(self._parse_hit(hit, index_name))

        start = (page - 1) * page_size if multi_index else 0
        page_hits = all_hits[start : start + page_size]

        return SearchResponse(
            results=page_hits,
            total=total,
            page=page,
            page_size=page_size,
            query=query,
        )

    def search(
        self,
        query: str,
        doc_type: str | None = None,
        owner_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """Full-text search across documents and files."""
        filters = self._build_filters(doc_type=doc_type, owner_id=owner_id)
        indices = self._resolve_indices(doc_type)
        response = self._run_search(query, indices, filters, page, page_size)
        record_search_analytics(query, response.total)
        return response

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
        """Advanced search with type/owner/tags/date-range filters."""
        filters = self._build_filters(
            doc_type=doc_type,
            owner_id=owner_id,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
        )
        indices = self._resolve_indices(doc_type)
        search_term = query or ""
        response = self._run_search(search_term, indices, filters, page, page_size)
        response = SearchResponse(
            results=response.results,
            total=response.total,
            page=page,
            page_size=page_size,
            query=search_term or "*",
        )
        record_search_analytics(search_term or "*", response.total)
        return response

    def suggest(self, prefix: str, size: int = 10) -> list[str]:
        """Prefix-first autocomplete suggestions.

        MeiliSearch is prefix-first out of the box; a plain OpenSearch ``match``
        query is NOT (it matches whole tokens). To keep type-ahead parity we use
        ``match_phrase_prefix`` against the ``search_as_you_type`` field and its
        shingled sub-fields, which matches on the last (partial) token.
        """
        suggestions: list[str] = []
        seen: set[str] = set()

        index_field = {
            self.documents_index_name: "title",
            self.files_index_name: "name",
        }
        for index_name, text_field in index_field.items():
            sayt = f"{text_field}.sayt"
            body = {
                "size": size,
                "_source": [text_field],
                "query": {
                    "multi_match": {
                        "query": prefix,
                        "type": "bool_prefix",
                        "fields": [sayt, f"{sayt}._2gram", f"{sayt}._3gram"],
                    }
                },
            }
            try:
                result = self.client.search(index=index_name, body=body)
            except OpenSearchException as exc:
                logger.warning("suggest_query_error", index=index_name, error=str(exc))
                continue
            for hit in result["hits"]["hits"]:
                text = hit["_source"].get(text_field, "")
                if text and text not in seen:
                    suggestions.append(text)
                    seen.add(text)
                    if len(suggestions) >= size:
                        return suggestions
        return suggestions

    # --- indexing ----------------------------------------------------------

    def index_document(self, document: dict[str, Any]) -> None:
        """Index or update a document."""
        doc = {**document, "type": "document"}
        self.client.index(
            index=self.documents_index_name,
            id=doc["id"],
            body=doc,
            refresh=True,
        )
        logger.info("document_indexed", document_id=doc.get("id"))

    def index_file(self, file_data: dict[str, Any]) -> None:
        """Index or update a file."""
        doc = {**file_data, "type": "file"}
        self.client.index(
            index=self.files_index_name,
            id=doc["id"],
            body=doc,
            refresh=True,
        )
        logger.info("file_indexed", file_id=doc.get("id"))

    def delete_document(self, doc_type: str, doc_id: str) -> bool:
        """Remove a document or file from the index. Returns False if not found."""
        index_name = (
            self.documents_index_name if doc_type == "document" else self.files_index_name
        )
        try:
            self.client.delete(index=index_name, id=doc_id, refresh=True)
        except NotFoundError:
            logger.warning("document_not_found_in_index", doc_id=doc_id, index=index_name)
            return False
        logger.info("document_removed_from_index", doc_id=doc_id, index=index_name)
        return True

    def reindex(
        self,
        documents: list[dict[str, Any]] | None = None,
        files: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Delete indices, recreate them, and optionally repopulate."""
        for index_name in [self.documents_index_name, self.files_index_name]:
            try:
                if self.client.indices.exists(index=index_name):
                    self.client.indices.delete(index=index_name)
                    logger.info("opensearch_index_deleted", index=index_name)
            except OpenSearchException:
                pass
        self.ensure_indices()

        indexed_counts: dict[str, int] = {"documents": 0, "files": 0}
        if documents:
            self._bulk_index(self.documents_index_name, documents, "document")
            indexed_counts["documents"] = len(documents)
        if files:
            self._bulk_index(self.files_index_name, files, "file")
            indexed_counts["files"] = len(files)

        return {
            "status": "reindexed",
            "indices": [self.documents_index_name, self.files_index_name],
            "indexed_counts": indexed_counts,
        }

    def _bulk_index(
        self, index_name: str, items: list[dict[str, Any]], doc_type: str
    ) -> None:
        """Bulk-index items in batches of 500."""
        for batch_start in range(0, len(items), 500):
            batch = items[batch_start : batch_start + 500]
            actions: list[dict[str, Any]] = []
            for item in batch:
                doc = {**item, "type": doc_type}
                actions.append({"index": {"_index": index_name, "_id": doc.get("id")}})
                actions.append(doc)
            if actions:
                self.client.bulk(body=actions, refresh=True)

    # --- parsing -----------------------------------------------------------

    def _parse_hit(self, hit: dict[str, Any], index_name: str) -> SearchHit:
        """Convert an OpenSearch hit to a SearchHit model."""
        source = hit.get("_source", {})
        highlight = hit.get("highlight", {})
        highlights: dict[str, list[str]] = {
            field: fragments
            for field, fragments in highlight.items()
            if field in _HIGHLIGHT_FIELDS
        }

        is_doc = index_name == self.documents_index_name
        content = source.get("content", "")
        return SearchHit(
            id=source.get("id", hit.get("_id", "")),
            title=source.get("title", "") if is_doc else source.get("name", ""),
            content_snippet=str(content)[:200] if is_doc else "",
            type=source.get("type", "document" if is_doc else "file"),
            owner_id=source.get("owner_id", ""),
            tags=source.get("tags", []),
            score=float(hit.get("_score") or 0.0),
            highlights=highlights,
            created_at=source.get("created_at"),
            updated_at=source.get("updated_at"),
            mime_type=source.get("mime_type"),
            folder_id=source.get("folder_id"),
            size=source.get("size"),
        )
