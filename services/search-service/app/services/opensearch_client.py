"""OpenSearch client for full-text search operations."""

import structlog
from opensearchpy import OpenSearch

logger = structlog.get_logger()

INDEX_NAME = "otterworks-documents"

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard", "fields": {"keyword": {"type": "keyword"}}},
            "content": {"type": "text", "analyzer": "standard"},
            "type": {"type": "keyword"},  # document, file
            "mime_type": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "folder_id": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "suggest": {"type": "completion"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


class OpenSearchService:
    def __init__(self, opensearch_url: str):
        self.client = OpenSearch(
            hosts=[opensearch_url],
            use_ssl=False,
            verify_certs=False,
        )
        self._ensure_index()

    def _ensure_index(self):
        """Create the index if it doesn't exist."""
        if not self.client.indices.exists(INDEX_NAME):
            self.client.indices.create(INDEX_NAME, body=INDEX_MAPPING)
            logger.info("opensearch_index_created", index=INDEX_NAME)

    def search(
        self,
        query: str,
        doc_type: str | None = None,
        owner_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Full-text search with optional filters."""
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content", "tags^2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        filter_clauses = []
        if doc_type:
            filter_clauses.append({"term": {"type": doc_type}})
        if owner_id:
            filter_clauses.append({"term": {"owner_id": owner_id}})

        body = {
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
                    "content": {"fragment_size": 200, "number_of_fragments": 3},
                }
            },
            "sort": ["_score", {"updated_at": {"order": "desc"}}],
        }

        response = self.client.search(index=INDEX_NAME, body=body)

        hits = []
        for hit in response["hits"]["hits"]:
            result = hit["_source"]
            result["_score"] = hit["_score"]
            result["_highlights"] = hit.get("highlight", {})
            hits.append(result)

        return {
            "results": hits,
            "total": response["hits"]["total"]["value"],
            "page": page,
            "page_size": page_size,
        }

    def suggest(self, prefix: str, size: int = 10) -> list[str]:
        """Autocomplete suggestions based on title prefix."""
        body = {
            "suggest": {
                "title-suggest": {
                    "prefix": prefix,
                    "completion": {"field": "suggest", "size": size},
                }
            }
        }

        response = self.client.search(index=INDEX_NAME, body=body)
        suggestions = []
        for option in response.get("suggest", {}).get("title-suggest", [{}])[0].get("options", []):
            suggestions.append(option["text"])
        return suggestions

    def index_document(self, document: dict):
        """Index or update a document."""
        doc_id = document.get("id")
        document["suggest"] = {"input": document.get("title", "").split()}
        self.client.index(index=INDEX_NAME, id=doc_id, body=document)

    def delete_document(self, document_id: str):
        """Remove a document from the index."""
        try:
            self.client.delete(index=INDEX_NAME, id=document_id)
        except Exception:
            logger.warning("document_not_found_in_index", document_id=document_id)
