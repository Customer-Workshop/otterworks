"""Search API endpoints."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import redis as redis_lib
import structlog
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.health import SEARCH_COUNT
from app.services.meilisearch_client import MeiliSearchService, get_search_analytics

logger = structlog.get_logger()

search_router = APIRouter(tags=["search"])

_redis_client: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    """Return a shared Redis client (lazy-initialised)."""
    global _redis_client
    if _redis_client is None:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _redis_client = redis_lib.Redis(host=host, port=port, decode_responses=True, socket_timeout=1)
    return _redis_client


def _chaos_active(key: str) -> bool:
    """Return True if the given chaos flag is set in Redis."""
    try:
        return bool(_get_redis().exists(key))
    except Exception:
        return False


def _get_service(request: Request) -> MeiliSearchService:
    """Get the shared MeiliSearchService from app state."""
    return request.app.state.search_service


# --- Pydantic models ---

class SearchHitModel(BaseModel):
    id: str
    title: str
    content_snippet: str
    type: str
    owner_id: str
    tags: list[str] = []
    score: float = 0.0
    highlights: dict[str, list[str]] = {}
    created_at: str | None = None
    updated_at: str | None = None
    mime_type: str | None = None
    folder_id: str | None = None
    size: int | None = None


class SearchResponseModel(BaseModel):
    results: list[SearchHitModel]
    total: int
    page: int
    page_size: int
    query: str


class SuggestResponseModel(BaseModel):
    suggestions: list[Any]
    query: str


class AdvancedSearchRequest(BaseModel):
    q: str | None = None
    type: str | None = None
    tags: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    page: int | str = 1
    size: int | str = 20


class AnalyticsResponseModel(BaseModel):
    popular_queries: list[dict[str, Any]]
    zero_result_queries: list[dict[str, Any]]
    total_searches: int
    avg_results_per_query: float


class ErrorResponse(BaseModel):
    error: str


# --- Endpoints ---

@search_router.get("/", response_model=SearchResponseModel)
async def search_documents(
    request: Request,
    q: str = Query(""),
    page: str = Query("1"),
    size: str = Query("20"),
    type: str | None = Query(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
):
    """Full-text search across documents and files."""
    try:
        page_int = max(1, int(page))
        page_size = max(1, min(100, int(size)))
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid page or size parameter"},
        )

    query = q
    if not query:
        return JSONResponse(
            status_code=400,
            content={"error": "Query parameter 'q' is required"},
        )

    owner_id = x_user_id.strip() if x_user_id else None
    doc_type = type

    try:
        service = _get_service(request)
        results = await asyncio.to_thread(
            service.search,
            query=query,
            doc_type=doc_type,
            owner_id=owner_id,
            page=page_int,
            page_size=page_size,
        )
        SEARCH_COUNT.inc()
        logger.info("search_executed", query=query, result_count=results.total)
        return JSONResponse(status_code=200, content=results.to_dict())
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        logger.exception("search_failed", query=query)
        return JSONResponse(status_code=500, content={"error": "Search failed"})


@search_router.get("/suggest", response_model=SuggestResponseModel)
async def suggest(
    request: Request,
    q: str = Query(""),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
):
    """Autocomplete suggestions based on prefix."""
    prefix = q
    if not prefix or len(prefix) < 2:
        return JSONResponse(
            status_code=200,
            content={"suggestions": [], "query": prefix},
        )

    if await asyncio.to_thread(_chaos_active, "chaos:search-service:suggest_500"):
        service = _get_service(request)
        raw_suggestions = await asyncio.to_thread(service.suggest, prefix)
        if not raw_suggestions:
            raw_suggestions = [{}]
        ranked = sorted(raw_suggestions, key=lambda s: s["_rankingScore"], reverse=True)
        return JSONResponse(status_code=200, content={"suggestions": ranked, "query": prefix})

    try:
        service = _get_service(request)
        suggestions = await asyncio.to_thread(service.suggest, prefix)
        return JSONResponse(
            status_code=200,
            content={"suggestions": suggestions, "query": prefix},
        )
    except Exception:
        logger.exception("suggest_failed", prefix=prefix)
        return JSONResponse(
            status_code=200,
            content={"suggestions": [], "query": prefix},
        )


@search_router.post("/advanced", response_model=SearchResponseModel)
async def advanced_search(
    request: Request,
    body: AdvancedSearchRequest | None = None,
    x_user_id: str | None = Header(None, alias="X-User-ID"),
):
    """Advanced search with filters: date range, owner, type, tags."""
    if body is None:
        body = AdvancedSearchRequest()

    query = body.q
    doc_type = body.type
    owner_id = x_user_id.strip() if x_user_id else None
    tags = body.tags
    date_from = body.date_from
    date_to = body.date_to

    try:
        page_int = max(int(body.page), 1)
        page_size = min(max(int(body.size), 1), 100)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid page or size parameter"},
        )

    try:
        service = _get_service(request)
        results = await asyncio.to_thread(
            service.advanced_search,
            query=query,
            doc_type=doc_type,
            owner_id=owner_id,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            page=page_int,
            page_size=page_size,
        )
        SEARCH_COUNT.inc()
        logger.info("advanced_search_executed", query=query, result_count=results.total)
        return JSONResponse(status_code=200, content=results.to_dict())
    except Exception:
        logger.exception("advanced_search_failed")
        return JSONResponse(
            status_code=500,
            content={"error": "Advanced search failed"},
        )


@search_router.get("/analytics", response_model=AnalyticsResponseModel)
async def search_analytics(
    x_user_id: str | None = Header(None, alias="X-User-ID"),
):
    """Search analytics: popular queries, zero-result queries."""
    try:
        analytics = get_search_analytics()
        return JSONResponse(status_code=200, content=analytics.to_dict())
    except Exception:
        logger.exception("analytics_failed")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve analytics"},
        )
