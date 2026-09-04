"""Caller identity and object-level authorization dependencies.

The api-gateway authenticates the caller and forwards the authenticated user id
in ``X-User-ID``; a direct Authorization bearer token is accepted as well so the
service can still be called without the gateway in front of it. Where this
service can verify the token itself, the token is the identity.
"""

import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.document import Comment, Document
from app.services.document_service import DocumentService


def _get_jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "")


def _verified_claims(request: Request) -> dict | None:
    """Decode the bearer token, or None when there is nothing this service can verify."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    secret = _get_jwt_secret()
    if not secret:
        return None
    try:
        return jwt.decode(
            auth_header[len("Bearer "):], secret, algorithms=["HS256", "HS384"]
        )
    except jwt.PyJWTError:
        return None


def _header_user_id(request: Request) -> UUID | None:
    forwarded_user_id = request.headers.get("X-User-ID")
    if not forwarded_user_id:
        return None
    try:
        return UUID(str(forwarded_user_id))
    except ValueError:
        return None


def extract_caller_id(request: Request) -> UUID | None:
    """Return the caller's user id, or None when the request is anonymous.

    ``X-User-ID`` is only as trustworthy as whoever set it, so a token this service
    can verify itself outranks it: the header is honoured only when it agrees with
    the token, and a verified token carrying no identity is not an identity.
    """
    claims = _verified_claims(request)
    header_user_id = _header_user_id(request)
    if claims is None:
        return header_user_id

    user_id_str = claims.get("sub") or claims.get("user_id")
    if not user_id_str:
        return None
    try:
        token_user_id = UUID(str(user_id_str))
    except ValueError:
        return None

    if header_user_id is not None and header_user_id != token_user_id:
        return None
    return token_user_id


def require_caller_id(request: Request) -> UUID:
    """Return the caller's user id, 401 when the request carries no identity."""
    caller_id = extract_caller_id(request)
    if not caller_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return caller_id


def ensure_owner(document: object, caller_id: UUID) -> None:
    """403 unless the caller owns the resource."""
    if getattr(document, "owner_id", None) != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )


async def get_owned_document(
    document_id: UUID,
    caller_id: UUID = Depends(require_caller_id),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Resolve the path document and require the caller to own it."""
    document = await DocumentService(db).get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    ensure_owner(document, caller_id)
    return document


async def get_deletable_comment(
    comment_id: UUID,
    document_id: UUID,
    caller_id: UUID = Depends(require_caller_id),
    db: AsyncSession = Depends(get_db),
) -> Comment:
    """Resolve the path comment, deletable by its author or the document owner."""
    service = DocumentService(db)
    document = await service.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    comment = await service.get_comment(document_id, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if caller_id not in (comment.author_id, document.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    return comment
