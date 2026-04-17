"""OtterWorks Search Service - Full-text search via OpenSearch."""

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
from app.services.opensearch_client import OpenSearchService
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


def create_app(config: AppConfig | None = None) -> Flask:
    """Create and configure the Flask application."""
    if config is None:
        config = AppConfig()

    configure_logging(config.log_level)

    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000", "http://localhost:4200"])

    # Store config on the app
    app.config["APP_CONFIG"] = config

    # Initialize OpenSearch service
    opensearch_service = OpenSearchService(config.opensearch)
    app.config["OPENSEARCH_SERVICE"] = opensearch_service

    # Try to create indices on startup (non-fatal if OpenSearch is not available)
    try:
        opensearch_service.ensure_indices()
        logger.info("opensearch_indices_ensured")
    except Exception:
        logger.warning("opensearch_indices_creation_deferred", reason="OpenSearch not available")

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(search_bp, url_prefix="/api/v1/search")
    app.register_blueprint(index_bp, url_prefix="/api/v1/search")

    # Prometheus request instrumentation
    @app.before_request
    def _start_timer() -> None:
        g.start_time = time.monotonic()

    @app.after_request
    def _record_metrics(response):  # type: ignore[no-untyped-def]
        if flask_request.path in ("/metrics", "/health"):
            return response
        elapsed = time.monotonic() - g.get("start_time", time.monotonic())
        endpoint = flask_request.path
        method = flask_request.method
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        return response

    # Start SQS consumer if enabled
    if config.sqs.enabled:
        from app.services.indexer import Indexer

        indexer = Indexer(opensearch_service)
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

    logger.info(
        "search_service_created",
        port=config.port,
        opensearch_url=config.opensearch.url,
        sqs_enabled=config.sqs.enabled,
    )
    return app


if __name__ == "__main__":
    app_config = AppConfig()
    app = create_app(app_config)
    app.run(host=app_config.host, port=app_config.port, debug=app_config.debug)
