"""Authentication middleware for the search service.

Public endpoints (health, metrics) are exempt. All other endpoints accept
either of two authentication modes:

* A valid service-to-service token via ``Authorization: Bearer <token>``
  (used by trusted internal callers such as the SQS indexer or admin
  reindex jobs).
* The ``X-User-ID`` header injected by the API gateway after it has
  validated the caller's JWT (used by user-facing requests proxied
  through the gateway). The gateway also attaches an
  ``X-User-ID-Signature`` header containing an HMAC-SHA256 of the user id
  computed with a secret shared with this service. The header is trusted
  only when this signature is valid, which prevents a client from
  spoofing an identity by talking to the service directly.

If a service token is configured the middleware will accept it on any
endpoint; if it is not configured (e.g. local dev), only the gateway
identity path is available and internal endpoints become reachable only
via the gateway.
"""

from __future__ import annotations

import hashlib
import hmac

import structlog
from flask import jsonify, request

logger = structlog.get_logger()

PUBLIC_PREFIXES = ("/health", "/metrics")


def require_auth(app):
    """Register a ``before_request`` hook that enforces authentication.

    * Requests to health/metrics paths are always allowed.
    * All other requests must present either a valid service token in
      the ``Authorization`` header or an ``X-User-ID`` header set by
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
        if auth_config.service_token:
            token = _extract_bearer_token()
            if token and token == auth_config.service_token:
                return None

        # Otherwise require a gateway-injected user identity whose signature
        # verifies against the shared secret. Trusting the raw header alone
        # would let anyone with network access to this service spoof any user.
        user_id = request.headers.get("X-User-ID", "").strip()
        if user_id and _verify_gateway_signature(user_id, auth_config.gateway_signing_secret):
            return None

        endpoint = request.endpoint or ""
        logger.warning("auth_rejected", endpoint=endpoint, path=path)
        return jsonify({"error": "unauthorized"}), 401


def _verify_gateway_signature(user_id: str, secret: str) -> bool:
    """Return True if the request carries a valid gateway identity signature.

    The API gateway signs the user id with HMAC-SHA256 using a shared secret
    and sends the hex digest in the ``X-User-ID-Signature`` header. If no
    shared secret is configured the header cannot be verified, so the identity
    is rejected rather than trusted.
    """
    if not secret:
        return False
    provided = request.headers.get("X-User-ID-Signature", "").strip()
    if not provided:
        return False
    expected = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
