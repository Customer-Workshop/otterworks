"""Health check and metrics endpoints."""

from __future__ import annotations

import structlog
from flask import Blueprint, current_app, jsonify
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
)

logger = structlog.get_logger()

health_bp = Blueprint("health", __name__)

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


@health_bp.route("/health")
def health() -> tuple:
    """Health check endpoint that verifies OpenSearch connectivity."""
    opensearch_service = current_app.config.get("OPENSEARCH_SERVICE")

    opensearch_healthy = False
    if opensearch_service:
        opensearch_healthy = opensearch_service.ping()

    status = "healthy" if opensearch_healthy else "degraded"
    http_status = 200 if opensearch_healthy else 503

    return jsonify({
        "status": status,
        "service": "search-service",
        "dependencies": {
            "opensearch": "connected" if opensearch_healthy else "disconnected",
        },
    }), http_status


@health_bp.route("/metrics")
def metrics() -> tuple:
    """Prometheus metrics endpoint."""
    return (
        generate_latest(),
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )
