"""Shared test fixtures."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.documents import require_user_id
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Comment, Document, DocumentVersion, Template  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
TEST_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

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


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    # The gateway resolves the caller upstream; the suite drives the ASGI app
    # directly, so it supplies the same identity it creates its documents with.
    app.dependency_overrides[require_user_id] = lambda: TEST_OWNER_ID
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def owner_id() -> uuid.UUID:
    return TEST_OWNER_ID


@pytest.fixture
async def unauthenticated_client(
    client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    """A client whose identity is resolved from the request, as in production."""
    app.dependency_overrides.pop(require_user_id, None)
    yield client


@pytest.fixture
def folder_id() -> uuid.UUID:
    return uuid.uuid4()
