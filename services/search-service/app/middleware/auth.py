"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. Internal indexing and admin
endpoints require a valid service-to-service token via the
``Authorization: Bearer <token>`` header. Search endpoints served through
the API gateway receive user identity via the ``X-User-ID`` header
injected by the gateway's JWT middleware — no extra token is required for
those, but the header must be present.
"""

from __future__ import annotations

import structlog
from flask import jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")

INTERNAL_ENDPOINTS = frozenset({
    "index.index_document",
    "index.index_file",
    "index.remove_from_index",
    "index.reindex",
})


def require_auth(app):
    """Register a ``before_request`` hook that enforces authentication.

    * Requests to health/metrics paths are always allowed.
    * Requests to internal indexing/admin endpoints must carry a valid
      service token in the ``Authorization`` header.
    * Requests to search endpoints must carry the ``X-User-ID`` header
      set by the API gateway (proving the user passed JWT validation).
    """
    auth_config = app.config["APP_CONFIG"].auth

    @app.before_request
    def _check_auth():
        if not auth_config.require_auth:
            return None

        path = request.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return None

        endpoint = request.endpoint or ""

        if endpoint in INTERNAL_ENDPOINTS:
            token = _extract_bearer_token()
            if not auth_config.service_token:
                logger.warning("auth_service_token_not_configured")
                return jsonify({"error": "unauthorized — service token not configured"}), 401
            if token != auth_config.service_token:
                logger.warning("auth_rejected_internal", endpoint=endpoint)
                return jsonify({"error": "unauthorized"}), 401
            return None

        user_id = request.headers.get("X-User-ID", "").strip()
        if not user_id:
            logger.warning("auth_missing_user_id", endpoint=endpoint)
            return jsonify({"error": "unauthorized — missing user identity"}), 401
        return None


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
