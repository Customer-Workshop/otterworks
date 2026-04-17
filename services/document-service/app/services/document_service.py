"""Document business logic service."""

from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.schemas.document import DocumentCreate, DocumentUpdate

logger = structlog.get_logger()


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: DocumentCreate) -> Document:
        document = Document(
            title=data.title,
            content=data.content,
            content_type=data.content_type,
            owner_id=data.owner_id,
            folder_id=data.folder_id,
            is_template=data.is_template,
            word_count=len(data.content.split()) if data.content else 0,
        )
        self.db.add(document)
        await self.db.flush()

        # Create initial version
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            content=data.content,
            created_by=data.owner_id,
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(document)

        return document

    async def get(self, document_id: UUID) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == document_id, Document.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        owner_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Document]:
        query = select(Document).where(Document.is_deleted.is_(False))
        if owner_id:
            query = query.where(Document.owner_id == owner_id)
        query = query.offset((page - 1) * page_size).limit(page_size)
        query = query.order_by(Document.updated_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(
        self, document_id: UUID, data: DocumentUpdate, updated_by: UUID | None = None
    ) -> Document | None:
        document = await self.get(document_id)
        if not document:
            return None

        content_changed = False
        if "title" in data.model_fields_set and data.title is not None:
            document.title = data.title
        if "content" in data.model_fields_set and data.content is not None:
            document.content = data.content
            document.word_count = len(data.content.split()) if data.content else 0
            content_changed = True
        if "folder_id" in data.model_fields_set:
            document.folder_id = data.folder_id

        # Create a new version record when content changes
        if content_changed:
            latest = await self.db.execute(
                select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                    DocumentVersion.document_id == document_id
                )
            )
            next_version = latest.scalar_one() + 1
            version = DocumentVersion(
                document_id=document_id,
                version_number=next_version,
                content=data.content,
                created_by=updated_by or document.owner_id,
            )
            self.db.add(version)

        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def delete(self, document_id: UUID) -> bool:
        document = await self.get(document_id)
        if not document:
            return False
        document.is_deleted = True
        await self.db.commit()
        return True

    async def list_versions(self, document_id: UUID) -> list[DocumentVersion]:
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        return list(result.scalars().all())
