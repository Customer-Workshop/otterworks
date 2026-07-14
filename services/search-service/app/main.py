"""OtterWorks Search Service - Full-text search via MeiliSearch."""

from __future__ import annotations

import logging
import sys
import time

import structlog
from flask import Flask, g, request as flask_request
from flask_cors import CORS

from app.api.health import REQUEST_COUNT, REQUEST_LATENCY, health_bp
from app.api.index import index_bp
from app.api.search import search_bp
from app.config import AppConfig
from app.middleware.auth import require_auth
from app.services.meilisearch_client import MeiliSearchService
from app.services.sqs_consumer import SQSConsumer

logger = structlog.get_logger()


def build_search_service(config: AppConfig):  # type: ignore[no-untyped-def]
    """Instantiate the search backend adapter selected by ``SEARCH_BACKEND``.

    Defaults to the self-managed MeiliSearch backend (the golden before-state).
    Set ``SEARCH_BACKEND=opensearch`` to use the Amazon OpenSearch adapter.
    Both adapters satisfy the same interface, so the API layer is unchanged.
    """
    if config.search_backend == "opensearch":
        from app.services.opensearch_client import OpenSearchService

        return OpenSearchService(config.opensearch)
    return MeiliSearchService(config.meilisearch)


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


def create_app(config: AppConfig | None = None) -> Flask:
    """Create and configure the Flask application."""
    if config is None:
        config = AppConfig()

    configure_logging(config.log_level)

    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000", "http://localhost:4200"])

    # Store config on the app
    app.config["APP_CONFIG"] = config

    # Initialize the selected search backend adapter (MeiliSearch by default,
    # OpenSearch when SEARCH_BACKEND=opensearch).
    search_service = build_search_service(config)
    app.config["SEARCH_SERVICE"] = search_service

    # Try to create indices on startup (non-fatal if the backend is unavailable)
    try:
        search_service.ensure_indices()
        logger.info("search_indices_ensured", backend=config.search_backend)
    except Exception:
        logger.warning("search_indices_creation_deferred", backend=config.search_backend, reason="backend not available")

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(search_bp, url_prefix="/api/v1/search")
    app.register_blueprint(index_bp, url_prefix="/api/v1/search")

    # Register authentication middleware
    require_auth(app)

    # Prometheus request instrumentation
    @app.before_request
    def _start_timer() -> None:
        g.start_time = time.monotonic()

    @app.after_request
    def _record_metrics(response):  # type: ignore[no-untyped-def]
        if flask_request.path in ("/metrics", "/health"):
            return response
        elapsed = time.monotonic() - g.get("start_time", time.monotonic())
        endpoint = flask_request.url_rule.rule if flask_request.url_rule else "unknown"
        method = flask_request.method
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        return response

    # Start SQS consumer if enabled
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
        app.config["SQS_CONSUMER"] = sqs_consumer

    backend_endpoint = (
        config.opensearch.endpoint
        if config.search_backend == "opensearch"
        else config.meilisearch.url
    )
    logger.info(
        "search_service_created",
        port=config.port,
        backend=config.search_backend,
        backend_endpoint=backend_endpoint,
        sqs_enabled=config.sqs.enabled,
    )
    return app


if __name__ == "__main__":
    app_config = AppConfig()
    app = create_app(app_config)
    app.run(host=app_config.host, port=app_config.port, debug=app_config.debug)
