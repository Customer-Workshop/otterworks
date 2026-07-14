"""Pydantic schemas for request/response validation."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    owner_id: UUID | None = None


class ItemUpdate(BaseModel):
    """Full replace (PUT)."""

    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")


class ItemPatch(BaseModel):
    """Partial update (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def reject_null_for_not_null_fields(cls, v: object, info) -> object:  # noqa: N805
        if info.field_name in ("name", "description") and v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class ItemResponse(BaseModel):
    id: UUID
    name: str
    description: str
    owner_id: UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    page: int
    size: int
    pages: int
