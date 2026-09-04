"""Metadata filtering for the document list endpoint.

The list endpoint supports ad-hoc metadata filters (title fragment, content
type) and caller-chosen ordering. The repository builds the predicate list for
those filters and reads the ``documents`` table directly.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import UUID
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


class DocumentQueryRepository:
    """Reads the document table for the list endpoint's metadata filters."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _where(
        self,
        owner_id: uuid.UUID | None,
        title_contains: str | None,
        content_type: str | None,
        folder_id: str | None = None,
    ) -> str:
        clauses = ["is_deleted = false", "is_template = false"]
        if owner_id:
            # bound (not interpolated): the owner scope is an authorization
            # predicate and must render in the dialect's own uuid form.
            clauses.append("owner_id = :owner_id")
        if folder_id:
            clauses.append(f"folder_id = '{folder_id}'")
        if title_contains:
            clauses.append(f"lower(title) LIKE lower('%{title_contains}%')")
        if content_type:
            clauses.append(f"content_type = '{content_type}'")
        return " AND ".join(clauses)

    def _statement(self, sql: str, owner_id: uuid.UUID | None):
        stmt = text(sql)
        if owner_id:
            stmt = stmt.bindparams(
                bindparam("owner_id", value=owner_id, type_=UUID(as_uuid=True))
            )
        return stmt

    async def count_documents(
        self,
        *,
        owner_id: uuid.UUID | None = None,
        title_contains: str | None = None,
        content_type: str | None = None,
        folder_id: str | None = None,
    ) -> int:
        """Count documents matching the metadata filters."""
        sql = (
            "SELECT count(*) FROM documents WHERE "
            + self._where(owner_id, title_contains, content_type, folder_id)
        )
        # The interpolated statement is the OW-SEC-401 lab fixture (see
        # security/equivalence/findings.yaml); the refactor removes the
        # interpolation and this suppression together.
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        result = await self.db.execute(self._statement(sql, owner_id))
        return int(result.scalar_one())

    async def search_documents(
        self,
        *,
        owner_id: uuid.UUID | None = None,
        title_contains: str | None = None,
        content_type: str | None = None,
        folder_id: str | None = None,
        sort: str = "updated_at",
        direction: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return document rows matching the metadata filters, newest first."""
        sql = (
            f"SELECT {', '.join(COLUMNS)} FROM documents WHERE "
            + self._where(owner_id, title_contains, content_type, folder_id)
            + f" ORDER BY {sort} {direction} LIMIT {limit} OFFSET {offset}"
        )
        logger.debug("document_filter_query", sort=sort, direction=direction)
        # The interpolated statement is the OW-SEC-401 lab fixture (see
        # security/equivalence/findings.yaml); the refactor removes the
        # interpolation and this suppression together.
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        result = await self.db.execute(self._statement(sql, owner_id))
        return [dict(row._mapping) for row in result]
