"""Identity handling on the per-document endpoints, resolved from the request."""

import os
import uuid

import jwt
import pytest
from httpx import AsyncClient

TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-pad32"  # noqa: S105
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


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
async def test_owner_can_read_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.get(
        f"/api/v1/documents/{doc_id}", headers=_auth(owner_id)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_unauthenticated_read_is_rejected(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_other_user_cannot_read_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.get(
        f"/api/v1/documents/{doc_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_delete_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_update_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.put(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Taken", "content": "Taken"},
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_patch_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Taken"},
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_list_versions(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.get(
        f"/api/v1/documents/{doc_id}/versions", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_restore_version(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)
    await unauthenticated_client.put(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Owned", "content": "Second body"},
        headers=_auth(owner_id),
    )
    versions = await unauthenticated_client.get(
        f"/api/v1/documents/{doc_id}/versions", headers=_auth(owner_id)
    )
    version_id = versions.json()[-1]["id"]

    resp = await unauthenticated_client.post(
        f"/api/v1/documents/{doc_id}/versions/{version_id}/restore",
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_write_is_rejected(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    for coro in (
        unauthenticated_client.put(
            f"/api/v1/documents/{doc_id}", json={"title": "T", "content": "C"}
        ),
        unauthenticated_client.patch(
            f"/api/v1/documents/{doc_id}", json={"title": "T"}
        ),
        unauthenticated_client.delete(f"/api/v1/documents/{doc_id}"),
        unauthenticated_client.post(f"/api/v1/documents/{doc_id}/share"),
    ):
        assert (await coro).status_code == 401


@pytest.mark.asyncio
async def test_other_user_cannot_export_document(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.get(
        f"/api/v1/documents/{doc_id}/export",
        params={"format": "html"},
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_user_cannot_mint_share_link(
    unauthenticated_client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(unauthenticated_client, owner_id)

    resp = await unauthenticated_client.post(
        f"/api/v1/documents/{doc_id}/share", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403
