"""Metadata filtering for the document list endpoint.

The list endpoint supports ad-hoc metadata filters (title fragment, content
type) and caller-chosen ordering. The repository builds the predicate list for
those filters and reads the ``documents`` table directly. Every caller value is
bound as a query parameter; ORDER BY is resolved from an allow-list.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import Boolean, Column, MetaData, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

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

SORTABLE_COLUMNS = frozenset(COLUMNS)
DIRECTIONS = {"asc": "ASC", "desc": "DESC"}
LIKE_ESCAPE = "\\"

# Lightweight Core view of the table: only the columns the filters touch need a
# real type, the rest are opaque and selected as-is.
documents = Table(
    "documents",
    MetaData(),
    *[
        Column(
            name,
            Boolean if name in ("is_deleted", "is_template") else String,
        )
        for name in COLUMNS
    ],
)


def _escape_like(fragment: str) -> str:
    """Escape LIKE metacharacters so the fragment matches literally."""
    return (
        fragment.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def resolve_order_by(sort: str, direction: str) -> str:
    """Return the ORDER BY clause for an allow-listed column and direction."""
    if sort not in SORTABLE_COLUMNS:
        raise ValueError(f"Unsupported sort column: {sort!r}")
    normalized = DIRECTIONS.get(str(direction).lower())
    if normalized is None:
        raise ValueError(f"Unsupported sort direction: {direction!r}")
    return f"{sort} {normalized}"


def _order_clause(sort: str, direction: str) -> ColumnElement[Any]:
    column_name, normalized = resolve_order_by(sort, direction).split(" ")
    column = documents.c[column_name]
    return column.desc() if normalized == "DESC" else column.asc()


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
        c = documents.c
        clauses: list[ColumnElement[bool]] = [c.is_deleted.is_(False), c.is_template.is_(False)]
        if owner_id:
            clauses.append(c.owner_id == str(owner_id))
        if folder_id:
            clauses.append(c.folder_id == str(folder_id))
        if title_contains:
            pattern = f"%{_escape_like(title_contains)}%"
            clauses.append(func.lower(c.title).like(func.lower(pattern), escape=LIKE_ESCAPE))
        if content_type:
            clauses.append(c.content_type == content_type)
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
        where = self._where(owner_id, title_contains, content_type, folder_id)
        stmt = select(func.count()).select_from(documents).where(*where)
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
        """Return document rows matching the metadata filters, newest first.

        Raises ``ValueError`` when ``sort`` or ``direction`` is not allow-listed.
        """
        order_by = _order_clause(sort, direction)
        where = self._where(owner_id, title_contains, content_type, folder_id)
        stmt = (
            select(*[documents.c[name] for name in COLUMNS])
            .where(*where)
            .order_by(order_by)
            .limit(int(limit))
            .offset(int(offset))
        )
        logger.debug("document_filter_query", sort=sort, direction=direction)
        result = await self.db.execute(stmt)
        return [dict(row._mapping) for row in result]
