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
    """Liveness check — returns 200 if the process is running.

    Used by Docker healthcheck (curl -f). Never calls external services
    so the response is immediate regardless of dependency health.
    Use /health/ready for dependency-aware readiness probes.
    """
    return jsonify({
        "status": "alive",
        "service": "search-service",
    }), 200


@health_bp.route("/health/ready")
def readiness() -> tuple:
    """Readiness check — returns 503 if OpenSearch is unreachable.

    Use this for load-balancer readiness probes to stop routing
    traffic when the service cannot serve search requests.
    """
    opensearch_service = current_app.config.get("OPENSEARCH_SERVICE")

    opensearch_healthy = False
    if opensearch_service:
        opensearch_healthy = opensearch_service.ping()

    if opensearch_healthy:
        return jsonify({"ready": True}), 200
    return jsonify({"ready": False, "reason": "opensearch_unavailable"}), 503


@health_bp.route("/metrics")
def metrics() -> tuple:
    """Prometheus metrics endpoint."""
    return (
        generate_latest(),
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )
