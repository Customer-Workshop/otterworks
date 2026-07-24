"""Health check and metrics endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

health_router = APIRouter()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "search_service_requests_total",
    "Total number of requests to the search service",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "search_service_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)
SEARCH_COUNT = Counter(
    "search_service_searches_total",
    "Total number of search queries executed",
)
INDEX_COUNT = Counter(
    "search_service_index_operations_total",
    "Total number of index operations",
    ["operation", "type"],
)


@health_router.get("/health")
async def health() -> dict:
    """Liveness check — returns 200 if the process is running."""
    return {
        "status": "alive",
        "service": "search-service",
    }


@health_router.get("/health/ready")
async def readiness(request: Request) -> Response:
    """Readiness check — returns 503 if MeiliSearch is unreachable."""
    search_service = request.app.state.search_service

    healthy = False
    if search_service:
        # The MeiliSearch SDK is synchronous; keep the event loop unblocked.
        healthy = await asyncio.to_thread(search_service.ping)

    if healthy:
        return JSONResponse({"ready": True}, status_code=200)
    return JSONResponse(
        {"ready": False, "reason": "meilisearch_unavailable"},
        status_code=503,
    )


@health_router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
