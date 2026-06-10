"""Health check and metrics endpoints."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Health check with DB connectivity verification."""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except (SQLAlchemyError, OSError):
        logger.exception("health_check_db_failed")
        db_status = "disconnected"

    status = "healthy" if db_status == "connected" else "degraded"
    return {
        "status": status,
        "service": "document-service",
        "checks": {"database": db_status},
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=(
            "# HELP document_service_up Document Service is running\n"
            "# TYPE document_service_up gauge\n"
            "document_service_up 1\n"
        )
    )
