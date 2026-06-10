"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. All other endpoints require
one of two authentication modes:

* A valid JWT in the ``Authorization: Bearer <token>`` header, validated
  independently by this service using the shared ``JWT_SECRET``.
* A valid service-to-service token via ``Authorization: Bearer <token>``
  (used by trusted internal callers such as the SQS indexer or admin
  reindex jobs).

The ``X-User-ID`` header (set by the API gateway) is read downstream for
tenant scoping but is no longer sufficient on its own — a valid JWT or
service token must accompany every request.
"""

from __future__ import annotations

import os

import jwt as pyjwt
import structlog
from flask import jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")


def require_auth(app):
    """Register a ``before_request`` hook that enforces authentication."""
    auth_config = app.config["APP_CONFIG"].auth

    @app.before_request
    def _check_auth():
        if not auth_config.require_auth:
            return None

        path = request.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return None

        # Accept a valid service token if one is configured.
        if auth_config.service_token:
            token = _extract_bearer_token()
            if token and token == auth_config.service_token:
                return None

        # Validate JWT independently — do not trust X-User-ID alone.
        bearer = _extract_bearer_token()
        jwt_secret = os.environ.get("JWT_SECRET", "")
        if bearer and jwt_secret:
            try:
                pyjwt.decode(bearer, jwt_secret, algorithms=["HS256", "HS384"])
                return None
            except pyjwt.PyJWTError:
                pass

        endpoint = request.endpoint or ""
        logger.warning("auth_rejected", endpoint=endpoint, path=path)
        return jsonify({"error": "unauthorized"}), 401


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
