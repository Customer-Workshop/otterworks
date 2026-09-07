"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. Every other request is
authenticated by exactly one of these modes, tried in order:

* A valid service-to-service token via ``Authorization: Bearer <token>``
  (trusted internal callers such as admin reindex jobs). Such callers may
  act on behalf of a user by supplying ``X-User-ID``.
* When ``JWT_SECRET`` is configured: a user JWT via
  ``Authorization: Bearer <jwt>`` signed with the shared secret. The owner
  id is taken from the validated ``sub``/``user_id`` claim only; any
  ``X-User-ID`` header on the request is ignored.
* When ``JWT_SECRET`` is *not* configured (legacy deployments): the
  ``X-User-ID`` header injected by the API gateway. This mode trusts the
  network boundary and is logged at startup.

The resolved identity is stored on ``flask.g`` and read by handlers via
:func:`current_owner_id`; handlers never read identity headers directly.
"""

from __future__ import annotations

import jwt
import structlog
from flask import g, jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")

AUTH_MODE_DISABLED = "disabled"
AUTH_MODE_SERVICE = "service"
AUTH_MODE_JWT = "jwt"
AUTH_MODE_GATEWAY_HEADER = "gateway_header"


def current_owner_id() -> str | None:
    """Owner id of the authenticated caller, or None when unscoped."""
    return g.get("owner_id")


def _set_identity(owner_id: str | None, mode: str) -> None:
    g.owner_id = owner_id or None
    g.auth_mode = mode


def _decode_user_jwt(token: str, secret: str, algorithms: tuple[str, ...]) -> str | None:
    """Return the user id from a validated JWT, or None if it is not acceptable."""
    try:
        claims = jwt.decode(token, secret, algorithms=list(algorithms))
    except jwt.PyJWTError as exc:
        logger.warning("jwt_rejected", reason=type(exc).__name__)
        return None
    user_id = claims.get("sub") or claims.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        logger.warning("jwt_rejected", reason="missing_subject")
        return None
    return user_id.strip()


def require_auth(app):
    """Register a ``before_request`` hook that authenticates every request."""
    auth_config = app.config["APP_CONFIG"].auth

    if auth_config.require_auth and not auth_config.jwt_secret:
        logger.warning(
            "auth_gateway_header_mode",
            detail="JWT_SECRET not set; trusting gateway-injected X-User-ID header",
        )

    @app.before_request
    def _check_auth():
        _set_identity(None, AUTH_MODE_DISABLED)
        if not auth_config.require_auth:
            return None

        path = request.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return None

        bearer = _extract_bearer_token()
        forwarded_user = request.headers.get("X-User-ID", "").strip()

        if auth_config.service_token and bearer and bearer == auth_config.service_token:
            _set_identity(forwarded_user, AUTH_MODE_SERVICE)
            return None

        if auth_config.jwt_secret:
            if bearer:
                user_id = _decode_user_jwt(
                    bearer, auth_config.jwt_secret, auth_config.jwt_algorithms
                )
                if user_id:
                    if forwarded_user and forwarded_user != user_id:
                        logger.warning("identity_header_mismatch_ignored", path=path)
                    _set_identity(user_id, AUTH_MODE_JWT)
                    return None
        elif forwarded_user:
            _set_identity(forwarded_user, AUTH_MODE_GATEWAY_HEADER)
            return None

        endpoint = request.endpoint or ""
        logger.warning("auth_rejected", endpoint=endpoint, path=path)
        return jsonify({"error": "unauthorized"}), 401


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
