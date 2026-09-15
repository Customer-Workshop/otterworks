"""Shared test fixtures."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Uuid
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Comment, Document, DocumentVersion, Template  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _store_uuids_as_postgres_renders_them() -> None:
    """Make SQLite hold uuids hyphenated, the way Postgres renders one as text.

    SQLite has no uuid type, so SQLAlchemy stores bare hex there. The metadata
    filter repository compares the caller's uuid *as text*, which would never
    match on SQLite and would silently return an empty list for every
    owner-scoped listing. Mirrors security/equivalence/harness.
    """

    def bind_processor(self, dialect):  # noqa: ANN001, ANN202 - SQLAlchemy hook
        def process(value):  # noqa: ANN001, ANN202
            return None if value is None else str(value)

        return process

    Uuid.bind_processor = bind_processor


_store_uuids_as_postgres_renders_them()

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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def folder_id() -> uuid.UUID:
    return uuid.uuid4()
