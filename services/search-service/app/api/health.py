"""Health check endpoints."""

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "search-service"})


@health_bp.route("/metrics")
def metrics():
    return (
        "# HELP search_service_up Search Service is running\n"
        "# TYPE search_service_up gauge\nsearch_service_up 1\n",
        200,
        {"Content-Type": "text/plain"},
    )
