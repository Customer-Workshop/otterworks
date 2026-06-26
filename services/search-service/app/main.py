"""OtterWorks Search Service - Full-text search via MeiliSearch."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.health import REQUEST_COUNT, REQUEST_LATENCY, health_router
from app.api.index import index_router
from app.api.search import search_router
from app.config import AppConfig
from app.middleware.auth import AuthMiddleware
from app.services.meilisearch_client import MeiliSearchService
from app.services.sqs_consumer import SQSConsumer

logger = structlog.get_logger()


def configure_logging(log_level: str) -> None:
    """Configure structured JSON logging via structlog."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for Prometheus."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/metrics", "/health"):
            return await call_next(request)
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        route = request.scope.get("route")
        endpoint = route.path if route else "unknown"
        REQUEST_COUNT.labels(
            method=request.method, endpoint=endpoint, status=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(elapsed)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    config: AppConfig = app.state.config

    configure_logging(config.log_level)

    # Initialize MeiliSearch service
    search_service = MeiliSearchService(config.meilisearch)
    app.state.search_service = search_service

    # Try to create indices on startup (non-fatal if MeiliSearch is not available)
    try:
        await asyncio.to_thread(search_service.ensure_indices)
        logger.info("meilisearch_indices_ensured")
    except Exception:
        logger.warning("meilisearch_indices_creation_deferred", reason="MeiliSearch not available")

    # Start SQS consumer if enabled
    sqs_consumer: SQSConsumer | None = None
    if config.sqs.enabled:
        from app.services.indexer import Indexer

        indexer = Indexer(search_service)
        sqs_consumer = SQSConsumer(
            indexer=indexer,
            queue_url=config.sqs.queue_url,
            region=config.sqs.region,
            endpoint_url=config.sqs.endpoint_url,
            max_messages=config.sqs.max_messages,
            wait_time_seconds=config.sqs.wait_time_seconds,
            visibility_timeout=config.sqs.visibility_timeout,
        )
        sqs_consumer.start()

    logger.info(
        "search_service_created",
        port=config.port,
        meilisearch_url=config.meilisearch.url,
        sqs_enabled=config.sqs.enabled,
    )

    yield

    # Shutdown
    if sqs_consumer:
        sqs_consumer.stop()


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = AppConfig()

    configure_logging(config.log_level)

    app = FastAPI(title="OtterWorks Search Service", lifespan=lifespan)
    app.state.config = config

    # Middleware stack (Starlette: last-added = outermost).
    # Execution order: Prometheus → CORS → Auth → App
    # This ensures: preflight OPTIONS handled before auth, metrics see all
    # responses, and auth-rejected 401s get CORS headers on the way back.
    app.add_middleware(AuthMiddleware, auth_config=config.auth)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:4200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(PrometheusMiddleware)

    # Include routers
    app.include_router(health_router)
    app.include_router(search_router, prefix="/api/v1/search")
    app.include_router(index_router, prefix="/api/v1/search")

    return app


if __name__ == "__main__":
    import uvicorn

    app_config = AppConfig()
    application = create_app(app_config)
    uvicorn.run(application, host=app_config.host, port=app_config.port)
