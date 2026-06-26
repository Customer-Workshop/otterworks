"""Indexing API endpoints for documents and files."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.health import INDEX_COUNT
from app.services.indexer import Indexer
from app.services.meilisearch_client import MeiliSearchService

logger = structlog.get_logger()

index_router = APIRouter(tags=["index"])


def _get_indexer(request: Request) -> Indexer:
    """Get an Indexer instance from the app state."""
    search_service: MeiliSearchService = request.app.state.search_service
    return Indexer(search_service)


@index_router.post("/index/document")
async def index_document(request: Request):
    """Index a document (called by document-service or SQS)."""
    try:
        data = await request.json()
    except Exception:
        data = None
    if not data:
        return JSONResponse(status_code=400, content={"error": "Request body is required"})

    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.index_document, data)
        INDEX_COUNT.labels(operation="index", type="document").inc()
        logger.info("api_document_indexed", document_id=data.get("id"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        logger.exception("api_index_document_failed")
        return JSONResponse(status_code=500, content={"error": "Failed to index document"})


@index_router.post("/index/file")
async def index_file(request: Request):
    """Index a file (called by file-service or SQS)."""
    try:
        data = await request.json()
    except Exception:
        data = None
    if not data:
        return JSONResponse(status_code=400, content={"error": "Request body is required"})

    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.index_file, data)
        INDEX_COUNT.labels(operation="index", type="file").inc()
        logger.info("api_file_indexed", file_id=data.get("id"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        logger.exception("api_index_file_failed")
        return JSONResponse(status_code=500, content={"error": "Failed to index file"})


@index_router.delete("/index/{doc_type}/{doc_id}")
async def remove_from_index(doc_type: str, doc_id: str, request: Request):
    """Remove a document or file from the search index."""
    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.remove, doc_type, doc_id)
        if result["status"] == "not_found":
            return JSONResponse(status_code=404, content=result)
        INDEX_COUNT.labels(operation="delete", type=doc_type).inc()
        logger.info("api_document_removed", doc_type=doc_type, doc_id=doc_id)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        logger.exception("api_remove_from_index_failed")
        return JSONResponse(status_code=500, content={"error": "Failed to remove from index"})


@index_router.post("/reindex")
async def reindex(request: Request):
    """Reindex all data (admin operation)."""
    try:
        indexer = _get_indexer(request)
        result = await asyncio.to_thread(indexer.reindex)
        logger.info("api_reindex_triggered")
        return JSONResponse(status_code=200, content=result)
    except Exception:
        logger.exception("api_reindex_failed")
        return JSONResponse(status_code=500, content={"error": "Failed to reindex"})
