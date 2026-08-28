"""Metadata filtering for the document list endpoint.

The list endpoint supports ad-hoc metadata filters (title fragment, content
type) and caller-chosen ordering. The repository builds the predicate list for
those filters and reads the ``documents`` table directly.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import ColumnElement, column, func, select, table
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

COLUMNS = (
    "id",
    "title",
    "content",
    "content_type",
    "owner_id",
    "folder_id",
    "is_deleted",
    "is_template",
    "word_count",
    "version",
    "created_at",
    "updated_at",
)

DOCUMENTS = table("documents", *(column(name) for name in COLUMNS))

# ORDER BY takes an identifier, which cannot be bound as a parameter, so the
# caller's choice is resolved through an allow-list.
SORT_COLUMNS = frozenset(COLUMNS)
SORT_DIRECTIONS = ("asc", "desc")


def _order_by(sort: str, direction: str) -> ColumnElement[Any]:
    """Resolve the caller's ordering through the column allow-list."""
    if sort not in SORT_COLUMNS:
        raise ArgumentError(f"unsupported sort column: {sort!r}")
    normalized = direction.lower() if direction else ""
    if normalized not in SORT_DIRECTIONS:
        raise ArgumentError(f"unsupported sort direction: {direction!r}")
    col = DOCUMENTS.c[sort]
    return col.asc() if normalized == "asc" else col.desc()


class DocumentQueryRepository:
    """Reads the document table for the list endpoint's metadata filters."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _where(
        self,
        owner_id: str | None,
        title_contains: str | None,
        content_type: str | None,
        folder_id: str | None = None,
    ) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = [
            DOCUMENTS.c.is_deleted == False,  # noqa: E712 - rendered as SQL, not Python
            DOCUMENTS.c.is_template == False,  # noqa: E712
        ]
        if owner_id:
            clauses.append(DOCUMENTS.c.owner_id == owner_id)
        if folder_id:
            clauses.append(DOCUMENTS.c.folder_id == folder_id)
        if title_contains:
            clauses.append(
                func.lower(DOCUMENTS.c.title).like(func.lower(f"%{title_contains}%"))
            )
        if content_type:
            clauses.append(DOCUMENTS.c.content_type == content_type)
        return clauses

    async def count_documents(
        self,
        *,
        owner_id: str | None = None,
        title_contains: str | None = None,
        content_type: str | None = None,
        folder_id: str | None = None,
    ) -> int:
        """Count documents matching the metadata filters."""
        stmt = (
            select(func.count())
            .select_from(DOCUMENTS)
            .where(*self._where(owner_id, title_contains, content_type, folder_id))
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def search_documents(
        self,
        *,
        owner_id: str | None = None,
        title_contains: str | None = None,
        content_type: str | None = None,
        folder_id: str | None = None,
        sort: str = "updated_at",
        direction: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return document rows matching the metadata filters, newest first."""
        stmt = (
            select(DOCUMENTS)
            .where(*self._where(owner_id, title_contains, content_type, folder_id))
            .order_by(_order_by(sort, direction))
            .limit(int(limit))
            .offset(int(offset))
        )
        logger.debug("document_filter_query", sort=sort, direction=direction)
        result = await self.db.execute(stmt)
        return [dict(row._mapping) for row in result]
