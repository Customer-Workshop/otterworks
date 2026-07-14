"""Shared test fixtures."""

import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Comment, Document, DocumentVersion, Template  # noqa: F401

TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-pad32"  # noqa: S105
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@asynccontextmanager
async def _test_client(
    db_session: AsyncSession,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers,
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def client(
    db_session: AsyncSession,
    owner_id: uuid.UUID,
) -> AsyncGenerator[AsyncClient, None]:
    token = jwt.encode(
        {"user_id": str(owner_id)},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    async with _test_client(
        db_session,
        headers={"Authorization": f"Bearer {token}"},
    ) as test_client:
        yield test_client


@pytest.fixture
async def unauthenticated_client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    async with _test_client(db_session) as test_client:
        yield test_client


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def folder_id() -> uuid.UUID:
    return uuid.uuid4()
