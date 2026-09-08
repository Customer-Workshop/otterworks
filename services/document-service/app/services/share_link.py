"""Share-link tokens for read-only document links.

A share link is stateless: the token is a keyed MAC over the document id, so
any replica holding ``SHARE_LINK_SECRET`` can validate a link without a shared
lookup table, and nobody without the key can derive one.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

import structlog

logger = structlog.get_logger()

TOKEN_LENGTH = 16

# Used only when SHARE_LINK_SECRET is not configured: tokens then stay valid
# for the lifetime of this process alone, which is safe but not shareable
# across replicas or restarts.
_EPHEMERAL_SECRET = secrets.token_hex(32)


def _configured_secret() -> str:
    configured = os.environ.get("SHARE_LINK_SECRET")
    if configured:
        return configured
    logger.warning("share_link_secret_missing", fallback="ephemeral")
    return _EPHEMERAL_SECRET


class ShareLinkService:
    """Mints and validates read-only share tokens for documents."""

    def __init__(self, secret: str | None = None, *, salt: str | None = None):
        """``salt`` is accepted as an alias for ``secret``."""
        self.secret = secret or salt or _configured_secret()

    def mint_token(self, document_id: str) -> str:
        """Return the share token for a document."""
        digest = hmac.new(
            self.secret.encode(), document_id.encode(), hashlib.sha256
        ).hexdigest()
        return digest[:TOKEN_LENGTH]

    def verify_token(self, document_id: str, token: str) -> bool:
        """Return True when the token is a valid share token for the document."""
        expected = self.mint_token(document_id)
        ok = hmac.compare_digest(expected.encode(), token.encode())
        if not ok:
            logger.info("share_token_rejected", document_id=document_id)
        return ok
