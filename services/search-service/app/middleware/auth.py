"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. Every other endpoint falls
into one of two classes:

* **Internal endpoints** (the ``index`` blueprint: index/reindex/remove)
  require the service-to-service token via ``Authorization: Bearer <token>``.
  A user JWT is never sufficient here.
* **User endpoints** (the ``search`` blueprint) require the caller's access
  JWT via ``Authorization: Bearer <jwt>``, forwarded unchanged by the API
  gateway. The user identity is taken from the validated token's
  ``sub``/``user_id`` claim and exposed as ``flask.g.user_id``. Inbound
  ``X-User-ID`` headers are never trusted, so a caller that reaches the pod
  directly cannot impersonate another user.

The service token is also accepted on user endpoints so trusted internal
callers can search across owners.

There is no switch to turn this off: a missing ``JWT_SECRET`` or
``SEARCH_SERVICE_TOKEN`` makes the corresponding class of request fail closed.
"""

from __future__ import annotations

import hmac

import jwt
import structlog
from flask import g, jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")
INTERNAL_BLUEPRINTS = frozenset({"index"})
JWT_ALGORITHMS = ["HS256", "HS384", "HS512"]
REFRESH_TOKEN_TYPE = "refresh"


def require_auth(app):
    """Register a ``before_request`` hook that enforces authentication.

    * Requests to health/metrics paths are always allowed.
    * Internal (index) endpoints require the configured service token.
    * All other endpoints require a valid user JWT (or the service token).
    """
    auth_config = app.config["APP_CONFIG"].auth

    if not auth_config.jwt_secret:
        logger.warning("jwt_secret_missing", detail="user endpoints will reject every request")
    if not auth_config.service_token:
        logger.warning("service_token_missing", detail="index endpoints will reject every request")

    @app.before_request
    def _check_auth():
        g.user_id = None

        path = request.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return None

        token = _extract_bearer_token()
        if token and _is_service_token(token, auth_config.service_token):
            return None

        user_id = _user_id_from_jwt(token, auth_config.jwt_secret) if token else None
        if not user_id:
            return _reject(401, "unauthorized")

        if request.blueprint in INTERNAL_BLUEPRINTS:
            return _reject(403, "forbidden")

        g.user_id = user_id
        return None


def _reject(status: int, error: str):
    logger.warning("auth_rejected", endpoint=request.endpoint or "", path=request.path, status=status)
    return jsonify({"error": error}), status


def _is_service_token(token: str, service_token: str) -> bool:
    """Constant-time comparison against the configured service token."""
    if not service_token:
        return False
    return hmac.compare_digest(token.encode("utf-8"), service_token.encode("utf-8"))


def _user_id_from_jwt(token: str, secret: str) -> str | None:
    """Return the user id from a valid JWT, or ``None`` if the token is not trusted."""
    if not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=JWT_ALGORITHMS)
    except jwt.PyJWTError:
        return None
    if payload.get("type") == REFRESH_TOKEN_TYPE:
        return None
    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        return None
    return str(user_id).strip() or None


def _extract_bearer_token() -> str | None:
    """Return the bearer token from the ``Authorization`` header, if present."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
