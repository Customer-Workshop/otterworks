"""Caller identity and tenant authorization for the billing HTTP layer.

Every tenant request must carry an ``Authorization: Bearer <token>`` credential
that this service verifies itself; forwarded identity headers are never trusted.

* Internal services (the parity harness, operator jobs) present the shared
  service token and may act on any tenant.
* Users present the platform access JWT issued by auth-service (HMAC-signed with
  the shared ``JWT_SECRET``). They may only act on tenants they are a member of
  according to ``billing_svc.tenant_members``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Path

from app.config import settings
from app.db import connect
from app.repository import PostgresPlansRepository

JWT_ALGORITHMS = ("HS256", "HS384")


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    is_service: bool


def _bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="authentication required")


def _is_service_token(token: str) -> bool:
    return bool(settings.service_token) and secrets.compare_digest(
        token.encode(), settings.service_token.encode()
    )


def _user_from_jwt(token: str) -> str:
    if not settings.jwt_secret:
        raise _unauthenticated()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=list(JWT_ALGORITHMS))
    except jwt.InvalidTokenError as error:
        raise _unauthenticated() from error
    user_id = claims.get("user_id") or claims.get("sub")
    if claims.get("type") != "access" or not user_id:
        raise _unauthenticated()
    return str(user_id)


def current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    token = _bearer_token(authorization)
    if not token:
        raise _unauthenticated()
    if _is_service_token(token):
        return Principal(user_id=None, is_service=True)
    return Principal(user_id=_user_from_jwt(token), is_service=False)


def require_service(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if not principal.is_service:
        raise HTTPException(status_code=403, detail="service credential required")
    return principal


def authorize_tenant(
    tenant_id: Annotated[UUID, Path()],
    principal: Annotated[Principal, Depends(current_principal)],
) -> UUID:
    if principal.is_service:
        return tenant_id
    with connect() as connection:
        is_member = PostgresPlansRepository(connection).is_tenant_member(
            tenant_id, principal.user_id or ""
        )
    if not is_member:
        raise HTTPException(status_code=403, detail="not authorized for this tenant")
    return tenant_id
