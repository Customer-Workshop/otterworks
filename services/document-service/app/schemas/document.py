"""Document Pydantic schemas for request/response validation."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="")
    content_type: str = Field(default="text/markdown")
    owner_id: UUID
    folder_id: UUID | None = None
    is_template: bool = False


class DocumentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    content: str | None = None
    folder_id: UUID | None = None


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    content: str
    content_type: str
    owner_id: UUID
    folder_id: UUID | None
    is_deleted: bool
    is_template: bool
    word_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    content: str
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
