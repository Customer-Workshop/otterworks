"""Metadata filtering for the document list endpoint.

The list endpoint supports ad-hoc metadata filters (title fragment, content
type) and caller-chosen ordering. The repository builds the predicate list for
those filters and reads the ``documents`` table directly.

Caller-supplied values are always bound as query parameters; the only caller
input that reaches SQL text is the sort column and direction, and both are
resolved through an allow-list.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import TextClause, Uuid, bindparam, text
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

SORTABLE_COLUMNS = frozenset(COLUMNS)
DIRECTIONS = {"asc": "ASC", "desc": "DESC"}


class InvalidSortError(ValueError):
    """The requested sort column or direction is not on the allow-list."""


def _order_by(sort: str, direction: str) -> str:
    if sort not in SORTABLE_COLUMNS:
        raise InvalidSortError("unsupported sort column")
    resolved_direction = DIRECTIONS.get(direction.lower())
    if resolved_direction is None:
        raise InvalidSortError("unsupported sort direction")
    return f"ORDER BY {sort} {resolved_direction}"


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
    ) -> tuple[str, dict[str, Any]]:
        """Return the WHERE predicate and the parameters it binds."""
        clauses = ["is_deleted = false", "is_template = false"]
        params: dict[str, Any] = {}
        if owner_id:
            clauses.append("owner_id = :owner_id")
            params["owner_id"] = owner_id
        if folder_id:
            clauses.append("folder_id = :folder_id")
            params["folder_id"] = folder_id
        if title_contains:
            clauses.append("lower(title) LIKE lower(:title_pattern)")
            params["title_pattern"] = f"%{title_contains}%"
        if content_type:
            clauses.append("content_type = :content_type")
            params["content_type"] = content_type
        return " AND ".join(clauses), params

    @staticmethod
    def _statement(sql: str, params: dict[str, Any]) -> TextClause:
        """Bind the uuid parameters with the column type so every dialect casts them."""
        statement = text(sql)
        uuid_params = [
            bindparam(name, type_=Uuid(as_uuid=False))
            for name in ("owner_id", "folder_id")
            if name in params
        ]
        return statement.bindparams(*uuid_params) if uuid_params else statement

    async def count_documents(
        self,
        *,
        owner_id: str | None = None,
        title_contains: str | None = None,
        content_type: str | None = None,
        folder_id: str | None = None,
    ) -> int:
        """Count documents matching the metadata filters."""
        where, params = self._where(owner_id, title_contains, content_type, folder_id)
        sql = f"SELECT count(*) FROM documents WHERE {where}"
        result = await self.db.execute(self._statement(sql, params), params)
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

        Raises ``InvalidSortError`` when ``sort`` is not a document column or
        ``direction`` is not ``asc``/``desc``.
        """
        where, params = self._where(owner_id, title_contains, content_type, folder_id)
        order_by = _order_by(sort, direction)
        sql = (
            f"SELECT {', '.join(COLUMNS)} FROM documents WHERE {where} "
            f"{order_by} LIMIT :limit OFFSET :offset"
        )
        params["limit"] = int(limit)
        params["offset"] = int(offset)
        logger.debug("document_filter_query", sort=sort, direction=direction)
        result = await self.db.execute(self._statement(sql, params), params)
        return [dict(row._mapping) for row in result]
