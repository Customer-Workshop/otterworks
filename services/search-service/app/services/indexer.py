"""Document and file indexing logic."""

from __future__ import annotations

from typing import Any

import structlog

from app.services.opensearch_client import OpenSearchService

logger = structlog.get_logger()


class Indexer:
    """Handles document and file indexing into OpenSearch."""

    def __init__(self, opensearch_service: OpenSearchService) -> None:
        self.opensearch = opensearch_service

    def index_document(self, payload: dict[str, Any]) -> dict[str, str]:
        """Validate and index a document.

        Expected payload fields:
            id, title, content, owner_id, tags, created_at, updated_at
        """
        if not payload.get("id"):
            raise ValueError("Document 'id' is required")
        if not payload.get("title"):
            raise ValueError("Document 'title' is required")

        document = {
            "id": payload["id"],
            "title": payload["title"],
            "content": payload.get("content", ""),
            "owner_id": payload.get("owner_id", ""),
            "tags": payload.get("tags", []),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

        self.opensearch.index_document(document)
        logger.info("indexer_document_indexed", document_id=document["id"])
        return {"status": "indexed", "id": document["id"], "type": "document"}

    def index_file(self, payload: dict[str, Any]) -> dict[str, str]:
        """Validate and index a file.

        Expected payload fields:
            id, name, mime_type, owner_id, folder_id, tags, size, created_at
        """
        if not payload.get("id"):
            raise ValueError("File 'id' is required")
        if not payload.get("name"):
            raise ValueError("File 'name' is required")

        file_data = {
            "id": payload["id"],
            "name": payload["name"],
            "mime_type": payload.get("mime_type", ""),
            "owner_id": payload.get("owner_id", ""),
            "folder_id": payload.get("folder_id", ""),
            "tags": payload.get("tags", []),
            "size": payload.get("size", 0),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

        self.opensearch.index_file(file_data)
        logger.info("indexer_file_indexed", file_id=file_data["id"])
        return {"status": "indexed", "id": file_data["id"], "type": "file"}

    def remove(self, doc_type: str, doc_id: str) -> dict[str, Any]:
        """Remove a document or file from the index."""
        if doc_type not in ("document", "file"):
            raise ValueError(f"Invalid type '{doc_type}'. Must be 'document' or 'file'.")

        deleted = self.opensearch.delete_document(doc_type, doc_id)
        status = "deleted" if deleted else "not_found"
        logger.info("indexer_document_removed", doc_id=doc_id, doc_type=doc_type, status=status)
        return {"status": status, "id": doc_id, "type": doc_type}

    def reindex(self) -> dict[str, Any]:
        """Trigger a full reindex (admin operation)."""
        result = self.opensearch.reindex()
        logger.info("indexer_reindex_complete")
        return result

    def process_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Process an SQS event message.

        Expected event format:
            {"action": "index_document"|"index_file"|"delete", "data": {...}}
        """
        action = event.get("action", "")
        data = event.get("data", {})

        if action == "index_document":
            return self.index_document(data)
        elif action == "index_file":
            return self.index_file(data)
        elif action == "delete":
            doc_type = data.get("type", "document")
            doc_id = data.get("id", "")
            return self.remove(doc_type, doc_id)
        else:
            logger.warning("indexer_unknown_action", action=action)
            return None
