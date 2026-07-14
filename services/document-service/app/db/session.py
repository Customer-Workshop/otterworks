"""Database session management."""

import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_recycle=settings.db_pool_recycle,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables, retrying the initial connection.

    Aurora Serverless v2 can be scaled to zero; the first connection after an
    idle period wakes the cluster and may briefly fail. Retrying keeps startup
    resilient. With the default retries=0 this behaves exactly as before.
    """
    attempts = settings.db_connect_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except (SQLAlchemyError, OSError) as exc:
            if attempt >= attempts:
                raise
            logger.warning(
                "init_db connection attempt %d/%d failed (%s); retrying in %.1fs",
                attempt,
                attempts,
                exc,
                settings.db_connect_retry_interval,
            )
            await asyncio.sleep(settings.db_connect_retry_interval)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for database sessions."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
