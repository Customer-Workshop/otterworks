"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. User-facing endpoints accept
the gateway-injected ``X-User-ID`` or a valid service token, while service-only
index endpoints always require the configured service token.
"""

from __future__ import annotations

import hmac
from functools import wraps

import structlog
from flask import current_app, jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")


def _service_token_valid(auth_config) -> bool:
    token = _extract_bearer_token()
    return bool(
        auth_config.service_token
        and token
        and hmac.compare_digest(token, auth_config.service_token)
    )


def require_service_token(view):
    """Require the configured service token for a service-only endpoint."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_config = current_app.config["APP_CONFIG"].auth
        if not auth_config.service_token:
            logger.warning("service_token_not_configured")
            return jsonify({"error": "forbidden"}), 403

        if not _service_token_valid(auth_config):
            logger.warning(
                "service_auth_rejected",
                endpoint=request.endpoint or "",
                path=request.path,
            )
            return jsonify({"error": "unauthorized"}), 401

        return view(*args, **kwargs)

    return wrapped


def require_auth(app):
    """Register a ``before_request`` hook that enforces authentication.

    * Requests to health/metrics paths are always allowed.
    * When enabled, all other requests must present either a valid service
      token in the ``Authorization`` header or an ``X-User-ID`` header set by
      the API gateway after JWT validation.
    """
    auth_config = app.config["APP_CONFIG"].auth

    @app.before_request
    def _check_auth():
        if not auth_config.require_auth:
            return None

        path = request.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return None

        # Accept a valid service token if one is configured.
        if auth_config.service_token and _service_token_valid(auth_config):
            return None

        # Otherwise require gateway-injected user identity.
        user_id = request.headers.get("X-User-ID", "").strip()
        if user_id:
            return None

        logger.warning("auth_rejected", endpoint=request.endpoint or "", path=path)
        return jsonify({"error": "unauthorized"}), 401


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
