"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "document-service"}


@router.get("/metrics")
async def metrics():
    return "# HELP document_service_up Document Service is running\n# TYPE document_service_up gauge\ndocument_service_up 1\n"
