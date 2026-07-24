"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. All other endpoints accept
either of two authentication modes:

* A valid service-to-service token via ``Authorization: Bearer <token>``
  (used by trusted internal callers such as the SQS indexer or admin
  reindex jobs).
* The ``X-User-ID`` header injected by the API gateway after it has
  validated the caller's JWT (used by user-facing requests proxied
  through the gateway).

If a service token is configured the middleware will accept it on any
endpoint; if it is not configured (e.g. local dev), only the gateway
identity path is available and internal endpoints become reachable only
via the gateway.
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce service-token or gateway-identity authentication."""

    async def dispatch(self, request: Request, call_next):
        auth_config = request.app.state.config.auth

        if not auth_config.require_auth:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Accept a valid service token if one is configured.
        if auth_config.service_token:
            token = _extract_bearer_token(request)
            if token and token == auth_config.service_token:
                return await call_next(request)

        # Otherwise require gateway-injected user identity.
        user_id = request.headers.get("X-User-ID", "").strip()
        if user_id:
            return await call_next(request)

        logger.warning("auth_rejected", path=path)
        return JSONResponse({"error": "unauthorized"}, status_code=401)


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
