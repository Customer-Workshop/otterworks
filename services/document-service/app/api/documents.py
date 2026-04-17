"""Document CRUD API endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.document import (
    DocumentCreate,
    DocumentFromTemplate,
    DocumentListResponse,
    DocumentPatch,
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


@router.get("/search", response_model=DocumentListResponse)
async def search_documents(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search documents by title or content."""
    service = DocumentService(db)
    items, total = await service.search(q, page=page, size=size)
    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=service.paginate(total, page, size),
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    owner_id: UUID | None = None,
    folder_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List documents with optional filtering and pagination."""
    service = DocumentService(db)
    items, total = await service.list_documents(
        owner_id=owner_id, folder_id=folder_id, page=page, size=size
    )
    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=service.paginate(total, page, size),
    )


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
    """Full replace of a document."""
    service = DocumentService(db)
    document = await service.update(document_id, body)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    logger.info("document_updated", document_id=str(document_id))
    return document


@router.patch("/{document_id}", response_model=DocumentResponse)
async def patch_document(
    document_id: UUID,
    body: DocumentPatch,
    db: AsyncSession = Depends(get_db),
):
    """Partial update of a document."""
    service = DocumentService(db)
    document = await service.patch(document_id, body)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    logger.info("document_patched", document_id=str(document_id))
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


@router.post(
    "/{document_id}/versions/{version_id}/restore",
    response_model=DocumentResponse,
)
async def restore_version(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Restore a document to a previous version."""
    service = DocumentService(db)
    document = await service.restore_version(document_id, version_id)
    if not document:
        raise HTTPException(
            status_code=404, detail="Document or version not found"
        )
    logger.info(
        "document_version_restored",
        document_id=str(document_id),
        version_id=str(version_id),
    )
    return document


@router.get("/{document_id}/export")
async def export_document(
    document_id: UUID,
    format: str = Query("markdown", pattern="^(pdf|html|markdown)$"),  # noqa: A002
    db: AsyncSession = Depends(get_db),
):
    """Export a document in the requested format."""
    service = DocumentService(db)
    document = await service.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    body, content_type = service.export_document(document, format)
    return PlainTextResponse(content=body, media_type=content_type)


@router.post(
    "/from-template/{template_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_from_template(
    template_id: UUID,
    body: DocumentFromTemplate,
    db: AsyncSession = Depends(get_db),
):
    """Create a document from a template."""
    service = DocumentService(db)
    document = await service.create_from_template(template_id, body)
    if not document:
        raise HTTPException(status_code=404, detail="Template not found")
    logger.info(
        "document_created_from_template",
        document_id=str(document.id),
        template_id=str(template_id),
    )
    return document
