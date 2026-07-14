"""Sample item CRUD API endpoints."""

import os
from uuid import UUID

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.item import (
    ItemCreate,
    ItemListResponse,
    ItemPatch,
    ItemResponse,
    ItemUpdate,
)
from app.services.sample_service import SampleService

logger = structlog.get_logger()
router = APIRouter()


def _get_jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "")


def _extract_user_id(request: Request) -> UUID | None:
    """Extract user ID from the Authorization JWT."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        secret = _get_jwt_secret()
        if secret:
            try:
                payload = jwt.decode(token, secret, algorithms=["HS256", "HS384"])
                user_id_str = payload.get("user_id") or payload.get("sub")
                if user_id_str:
                    return UUID(str(user_id_str))
            except (jwt.PyJWTError, ValueError):
                pass
        else:
            forwarded_user_id = request.headers.get("X-User-ID")
            if forwarded_user_id:
                try:
                    return UUID(str(forwarded_user_id))
                except ValueError:
                    pass

    return None


def _require_user_id(request: Request) -> UUID:
    user_id = _extract_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _ensure_owner(item: object, user_id: UUID) -> None:
    if getattr(item, "owner_id", None) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")


async def _do_create_item(
    body: ItemCreate,
    request: Request,
    db: AsyncSession,
) -> ItemResponse:
    if not body.owner_id:
        extracted_id = _extract_user_id(request)
        if not extracted_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="owner_id is required: provide it in the body or authenticate via JWT",
            )
        body.owner_id = extracted_id

    service = SampleService(db)
    item = await service.create(body)
    logger.info("item_created", item_id=str(item.id))
    return item


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new item."""
    return await _do_create_item(body, request, db)


@router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_item_no_slash(
    body: ItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new item (no trailing slash)."""
    return await _do_create_item(body, request, db)


async def _do_list_items(
    owner_id: UUID | None,
    page: int,
    size: int,
    db: AsyncSession,
) -> ItemListResponse:
    service = SampleService(db)
    items, total = await service.list_items(owner_id=owner_id, page=page, size=size)
    return ItemListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=service.paginate(total, page, size),
    )


@router.get("/", response_model=ItemListResponse)
async def list_items(
    request: Request,
    owner_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List items with optional filtering and pagination."""
    effective_owner = owner_id or _extract_user_id(request)
    return await _do_list_items(effective_owner, page, size, db)


@router.get(
    "",
    response_model=ItemListResponse,
    include_in_schema=False,
)
async def list_items_no_slash(
    request: Request,
    owner_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List items (no trailing slash)."""
    effective_owner = owner_id or _extract_user_id(request)
    return await _do_list_items(effective_owner, page, size, db)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get an item by ID."""
    user_id = _require_user_id(request)
    service = SampleService(db)
    item = await service.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    _ensure_owner(item, user_id)
    return item


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    body: ItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Full replace of an item."""
    user_id = _require_user_id(request)
    service = SampleService(db)
    existing = await service.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    _ensure_owner(existing, user_id)
    item = await service.update(item_id, body)
    logger.info("item_updated", item_id=str(item_id))
    return item


@router.patch("/{item_id}", response_model=ItemResponse)
async def patch_item(
    item_id: UUID,
    body: ItemPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Partial update of an item."""
    user_id = _require_user_id(request)
    service = SampleService(db)
    existing = await service.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    _ensure_owner(existing, user_id)
    item = await service.patch(item_id, body)
    logger.info("item_patched", item_id=str(item_id))
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete an item (soft delete)."""
    user_id = _require_user_id(request)
    service = SampleService(db)
    existing = await service.get(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    _ensure_owner(existing, user_id)
    await service.delete(item_id)
    logger.info("item_deleted", item_id=str(item_id))
