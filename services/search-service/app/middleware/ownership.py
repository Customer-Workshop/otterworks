"""Object-level authorization for the indexing endpoints.

``require_auth`` only proves *who* the caller is; these decorators prove the
caller may act on the *record* they named.  Ownership is the ``owner_id`` of
the record already stored in MeiliSearch, compared against the ``X-User-ID``
header injected by the API gateway.

Callers presenting the configured service-to-service token (document-service,
file-service, the SQS indexer, admin jobs) are trusted to write arbitrary
``owner_id`` values and to run global operations.

Enforcement follows the same ``require_auth`` switch as the authentication
middleware, so a deployment with authentication disabled (local dev, tests)
behaves as before.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import structlog
from flask import current_app, g, jsonify, request

from app.middleware.auth import extract_bearer_token
from app.services.meilisearch_client import MeiliSearchService

logger = structlog.get_logger()

INDEXED_TYPES = ("document", "file")


def authz_enabled() -> bool:
    """Whether authorization is enforced for this deployment."""
    return current_app.config["APP_CONFIG"].auth.require_auth


def is_service_caller() -> bool:
    """Whether the request presents the configured service-to-service token."""
    service_token = current_app.config["APP_CONFIG"].auth.service_token
    return bool(service_token) and extract_bearer_token() == service_token


def caller_user_id() -> str:
    """The gateway-authenticated caller id, or an empty string when absent."""
    return request.headers.get("X-User-ID", "").strip()


def caller_owner_id() -> str | None:
    """Owner id to force on writes, or ``None`` for trusted service callers."""
    return g.get("caller_owner_id")


def _unauthenticated() -> tuple:
    logger.warning("ownership_unauthenticated", path=request.path)
    return jsonify({"error": "unauthorized"}), 401


def _forbidden(doc_type: str, doc_id: str, user_id: str) -> tuple:
    logger.warning("ownership_denied", doc_type=doc_type, doc_id=doc_id, user_id=user_id)
    return jsonify({"error": "forbidden"}), 403


def _indexed_owner_id(doc_type: str, doc_id: str) -> str | None:
    """Owner of the indexed record, or ``None`` when it is not indexed."""
    service: MeiliSearchService = current_app.config["SEARCH_SERVICE"]
    record = service.get_indexed_document(doc_type, doc_id)
    if record is None:
        return None
    return str(record.get("owner_id") or "")


def _authorize(doc_type: str, doc_id: str) -> tuple | None:
    """Reject callers who do not own the indexed record, if it exists.

    A record that is not indexed yet is not owned by anyone: the handler is
    allowed to run and reports its own 404 (delete) or creates it (upsert).
    """
    if is_service_caller():
        g.caller_owner_id = None
        return None

    user_id = caller_user_id()
    if not user_id:
        return _unauthenticated()

    owner_id = _indexed_owner_id(doc_type, doc_id)
    if owner_id is not None and owner_id != user_id:
        return _forbidden(doc_type, doc_id, user_id)

    g.caller_owner_id = user_id
    return None


def require_path_ownership(view: Callable[..., Any]) -> Callable[..., Any]:
    """Authorize routes whose record is named by ``<doc_type>/<doc_id>``."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        doc_type = kwargs.get("doc_type", "")
        if not authz_enabled() or doc_type not in INDEXED_TYPES:
            return view(*args, **kwargs)
        return _authorize(doc_type, kwargs.get("doc_id", "")) or view(*args, **kwargs)

    return wrapper


def require_payload_ownership(doc_type: str) -> Callable[..., Any]:
    """Authorize upsert routes whose record id comes from the request body."""

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not authz_enabled():
                return view(*args, **kwargs)
            payload = request.get_json(silent=True) or {}
            doc_id = str(payload.get("id") or "")
            return _authorize(doc_type, doc_id) or view(*args, **kwargs)

        return wrapper

    return decorator


def require_service_token(view: Callable[..., Any]) -> Callable[..., Any]:
    """Restrict a global (non per-record) operation to internal callers."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not authz_enabled() or is_service_caller():
            return view(*args, **kwargs)
        if not caller_user_id():
            return _unauthenticated()
        logger.warning("service_token_required", path=request.path)
        return jsonify({"error": "forbidden"}), 403

    return wrapper
