"""Shared test fixtures."""

import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Comment, Document, DocumentVersion, Template  # noqa: F401

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


@pytest.fixture
async def client_factory(
    db_session: AsyncSession,
) -> AsyncGenerator[Callable[..., object], None]:
    """Build clients that call the app as a given user (via ``X-User-ID``)."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncExitStack() as stack:

        async def _make(user_id: uuid.UUID | None = None) -> AsyncClient:
            headers = {"X-User-ID": str(user_id)} if user_id else {}
            return await stack.enter_async_context(
                AsyncClient(
                    transport=transport, base_url="http://test", headers=headers
                )
            )

        yield _make
    app.dependency_overrides.clear()


@pytest.fixture
async def client(client_factory, owner_id: uuid.UUID) -> AsyncClient:
    """Client authenticated as ``owner_id``."""
    return await client_factory(owner_id)


@pytest.fixture
async def anon_client(client_factory) -> AsyncClient:
    """Client that sends no identity headers."""
    return await client_factory()


@pytest.fixture
def other_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def other_client(client_factory, other_user_id: uuid.UUID) -> AsyncClient:
    """Client authenticated as a different user than ``owner_id``."""
    return await client_factory(other_user_id)


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def folder_id() -> uuid.UUID:
    return uuid.uuid4()
