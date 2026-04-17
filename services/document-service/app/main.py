"""OtterWorks Document Service - FastAPI application."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, health
from app.db.session import engine, init_db

logger = structlog.get_logger()

app = FastAPI(
    title="OtterWorks Document Service",
    description="Document CRUD, versioning, and content management",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])


@app.on_event("startup")
async def startup():
    logger.info("document_service_starting")
    await init_db()
    logger.info("document_service_started")


@app.on_event("shutdown")
async def shutdown():
    logger.info("document_service_shutting_down")
    await engine.dispose()
