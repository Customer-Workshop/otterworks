"""Caller identity and tenant authorization for the billing HTTP layer.

Two callers are trusted:

* Internal services (the parity harness, operator jobs) present the shared
  service token as ``Authorization: Bearer <token>`` and may act on any tenant.
* User-facing requests arrive through the API gateway, which validates the
  caller's JWT and injects ``X-User-ID`` together with the ``X-Tenant-ID`` the
  user belongs to. Such callers may only act on their own tenant.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path

from app.config import settings


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    tenant_id: UUID | None
    is_service: bool

    def can_access(self, tenant_id: UUID) -> bool:
        return self.is_service or self.tenant_id == tenant_id


def _bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def current_principal(
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> Principal:
    token = _bearer_token(authorization)
    if settings.service_token and token:
        if secrets.compare_digest(token, settings.service_token):
            return Principal(user_id=None, tenant_id=None, is_service=True)
        raise HTTPException(status_code=401, detail="invalid service token")

    user_id = (x_user_id or "").strip()
    if not user_id or not x_tenant_id:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        tenant_id = UUID(x_tenant_id.strip())
    except ValueError as error:
        raise HTTPException(status_code=401, detail="authentication required") from error
    return Principal(user_id=user_id, tenant_id=tenant_id, is_service=False)


def authorize_tenant(
    tenant_id: Annotated[UUID, Path()],
    principal: Annotated[Principal, Depends(current_principal)],
) -> UUID:
    if not principal.can_access(tenant_id):
        raise HTTPException(status_code=403, detail="not authorized for this tenant")
    return tenant_id
