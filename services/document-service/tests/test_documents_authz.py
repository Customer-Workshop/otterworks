"""Identity handling on the per-document endpoints with auth enforcement on."""

import os
import uuid

import jwt
import pytest
from httpx import AsyncClient

from app.config import settings

TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-pad32"  # noqa: S105
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def require_auth_enabled():
    original = settings.require_auth
    settings.require_auth = True
    yield
    settings.require_auth = original


def _auth(user_id: uuid.UUID) -> dict[str, str]:
    token = jwt.encode({"user_id": str(user_id)}, TEST_JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_document(client: AsyncClient, owner_id: uuid.UUID) -> str:
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Owned", "content": "Body", "owner_id": str(owner_id)},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_owner_can_read_document(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=_auth(owner_id))
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_unauthenticated_read_is_rejected(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_other_user_cannot_read_document(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.get(
        f"/api/v1/documents/{doc_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_delete_document(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_export_document(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/export",
        params={"format": "html"},
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ownership_is_enforced_with_auth_enforcement_off(
    client: AsyncClient, owner_id: uuid.UUID
):
    """A caller that presents an identity is owner-checked either way."""
    doc_id = await _create_document(client, owner_id)
    settings.require_auth = False

    resp = await client.get(
        f"/api/v1/documents/{doc_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403
