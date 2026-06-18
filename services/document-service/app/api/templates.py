"""Template API endpoints."""

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.document import TemplateCreate, TemplateResponse
from app.services.document_service import DocumentService

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", response_model=list[TemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
):
    """List all templates."""
    service = DocumentService(db)
    return await service.list_templates()


@router.post(
    "/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_template(
    body: TemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new template."""
    from app.api.documents import _extract_user_id
    user_id = _extract_user_id(request)
    if user_id:
        body.created_by = user_id
    service = DocumentService(db)
    template = await service.create_template(body)
    logger.info("template_created", template_id=str(template.id))
    return template
