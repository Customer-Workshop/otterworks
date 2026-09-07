"""Share-link tokens for read-only document links.

A share link is stateless: the token is an HMAC-SHA256 over the document id,
keyed with a server-held secret, so any replica holding the secret can validate
a link without a shared lookup table and nobody without it can derive one.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

import structlog

logger = structlog.get_logger()

TOKEN_LENGTH = 32
SECRET_ENV = "SHARE_LINK_SECRET"  # noqa: S105
FALLBACK_SECRET_ENV = "JWT_SECRET"  # noqa: S105

_ephemeral_secret: str | None = None


def _resolve_secret(explicit: str | None) -> str:
    """Return the keying material, preferring the configured secret.

    Without ``SHARE_LINK_SECRET`` the service falls back to ``JWT_SECRET`` so a
    default deployment keeps minting stable links; with neither, a random
    per-process key keeps tokens unforgeable at the cost of stability across
    restarts.
    """
    global _ephemeral_secret
    if explicit:
        return explicit
    for env_name in (SECRET_ENV, FALLBACK_SECRET_ENV):
        value = os.environ.get(env_name)
        if value:
            return value
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_hex(32)
        logger.warning("share_link_secret_missing", env=SECRET_ENV)
    return _ephemeral_secret


class ShareLinkService:
    """Mints and validates read-only share tokens for documents."""

    def __init__(self, salt: str | None = None, secret: str | None = None):
        # ``salt`` is kept as an alias of ``secret`` for existing callers.
        self.secret = _resolve_secret(secret or salt)

    def mint_token(self, document_id: str) -> str:
        """Return the share token for a document."""
        digest = hmac.new(
            self.secret.encode(), document_id.encode(), hashlib.sha256
        ).hexdigest()
        return digest[:TOKEN_LENGTH]

    def verify_token(self, document_id: str, token: str) -> bool:
        """Return True when the token is a valid share token for the document."""
        expected = self.mint_token(document_id)
        ok = hmac.compare_digest(expected.encode(), str(token).encode())
        if not ok:
            logger.info("share_token_rejected", document_id=document_id)
        return ok
