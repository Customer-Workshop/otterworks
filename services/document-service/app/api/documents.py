"""Document CRUD API endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
    DocumentVersionResponse,
)
from app.services.document_service import DocumentService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new document."""
    service = DocumentService(db)
    document = await service.create(body)
    logger.info("document_created", document_id=str(document.id))
    return document


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    owner_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List documents with optional filtering and pagination."""
    service = DocumentService(db)
    documents = await service.list(owner_id=owner_id, page=page, page_size=page_size)
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a document by ID."""
    service = DocumentService(db)
    document = await service.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a document."""
    service = DocumentService(db)
    document = await service.update(document_id, body)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    logger.info("document_updated", document_id=str(document_id))
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document (soft delete)."""
    service = DocumentService(db)
    deleted = await service.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    logger.info("document_deleted", document_id=str(document_id))


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
async def list_versions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List document versions."""
    service = DocumentService(db)
    versions = await service.list_versions(document_id)
    return versions
