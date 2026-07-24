"""Indexing API endpoints for documents and files."""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.health import INDEX_COUNT
from app.services.indexer import Indexer
from app.services.meilisearch_client import MeiliSearchService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/search", tags=["index"])


def _get_indexer(request: Request) -> Indexer:
    """Get an Indexer instance from application state."""
    search_service: MeiliSearchService = request.app.state.search_service
    return Indexer(search_service)


async def _get_json_body(request: Request) -> dict | None:
    """Parse the JSON request body, returning None when absent/invalid."""
    try:
        raw = await request.body()
        if not raw:
            return None
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


@router.post("/index/document")
async def index_document(request: Request) -> JSONResponse:
    """Index a document (called by document-service or SQS)."""
    data = await _get_json_body(request)
    if not data:
        return JSONResponse({"error": "Request body is required"}, status_code=400)

    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.index_document, data)
        INDEX_COUNT.labels(operation="index", type="document").inc()
        logger.info("api_document_indexed", document_id=data.get("id"))
        return JSONResponse(result, status_code=201)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        logger.exception("api_index_document_failed")
        return JSONResponse({"error": "Failed to index document"}, status_code=500)


@router.post("/index/file")
async def index_file(request: Request) -> JSONResponse:
    """Index a file (called by file-service or SQS)."""
    data = await _get_json_body(request)
    if not data:
        return JSONResponse({"error": "Request body is required"}, status_code=400)

    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.index_file, data)
        INDEX_COUNT.labels(operation="index", type="file").inc()
        logger.info("api_file_indexed", file_id=data.get("id"))
        return JSONResponse(result, status_code=201)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        logger.exception("api_index_file_failed")
        return JSONResponse({"error": "Failed to index file"}, status_code=500)


@router.delete("/index/{doc_type}/{doc_id}")
async def remove_from_index(doc_type: str, doc_id: str, request: Request) -> JSONResponse:
    """Remove a document or file from the search index."""
    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.remove, doc_type, doc_id)
        if result["status"] == "not_found":
            return JSONResponse(result, status_code=404)
        INDEX_COUNT.labels(operation="delete", type=doc_type).inc()
        logger.info("api_document_removed", doc_type=doc_type, doc_id=doc_id)
        return JSONResponse(result, status_code=200)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        logger.exception("api_remove_from_index_failed")
        return JSONResponse({"error": "Failed to remove from index"}, status_code=500)


@router.post("/reindex")
async def reindex(request: Request) -> JSONResponse:
    """Reindex all data (admin operation)."""
    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.reindex)
        logger.info("api_reindex_triggered")
        return JSONResponse(result, status_code=200)
    except Exception:
        logger.exception("api_reindex_failed")
        return JSONResponse({"error": "Failed to reindex"}, status_code=500)
