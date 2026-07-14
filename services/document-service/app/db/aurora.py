"""Aurora IAM authentication and TLS helpers for the PostgreSQL connection layer.

This is additive: when ``DOC_SVC_DB_IAM_AUTH_ENABLED`` is false (the default) the
engine behaves exactly as before (static password, no forced TLS), so the
existing RDS PostgreSQL wiring stays intact for revert. When enabled, physical
connections authenticate with a short-lived RDS IAM auth token and negotiate
TLS against the Aurora endpoint.
"""

from __future__ import annotations

import ssl as ssl_lib
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import settings


def _endpoint_from_url(database_url: str) -> tuple[str, int, str]:
    """Extract (host, port, user) from the configured SQLAlchemy URL."""
    parts = urlsplit(database_url)
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    user = parts.username or "otterworks"
    return host, port, user


def generate_auth_token() -> str:
    """Generate a short-lived RDS IAM authentication token (valid ~15 minutes)."""
    import boto3  # imported lazily so the default path never needs AWS creds

    host, port, user = _endpoint_from_url(settings.database_url)
    region = settings.db_iam_region or settings.aws_region
    client = boto3.client("rds", region_name=region)
    return client.generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user, Region=region
    )


def _build_ssl_context() -> ssl_lib.SSLContext | bool:
    """Build an asyncpg-compatible TLS context from the configured SSL mode."""
    mode = settings.db_ssl_mode.lower()
    if mode in ("", "disable", "allow", "prefer"):
        # Preserve prior behaviour: let the driver decide (no forced TLS).
        return False
    ctx = ssl_lib.create_default_context(cafile=settings.db_ssl_root_cert or None)
    if mode in ("require", "verify-ca") or not settings.db_ssl_root_cert:
        # `require` encrypts without server-cert verification; also used when no
        # CA bundle is provided for verify modes.
        ctx.check_hostname = False
        ctx.verify_mode = ssl_lib.CERT_NONE if mode == "require" else ssl_lib.CERT_REQUIRED
    else:  # verify-full
        ctx.check_hostname = True
        ctx.verify_mode = ssl_lib.CERT_REQUIRED
    return ctx


def configure_aurora(engine: AsyncEngine) -> None:
    """Attach IAM-token + TLS injection to an engine when Aurora auth is enabled."""
    if not settings.db_iam_auth_enabled:
        return

    ssl_ctx = _build_ssl_context()

    @event.listens_for(engine.sync_engine, "do_connect")
    def _provide_iam_token(_dialect: Any, _rec: Any, cargs: Any, cparams: dict) -> None:
        cparams["password"] = generate_auth_token()
        if ssl_ctx is not False:
            cparams["ssl"] = ssl_ctx
