"""Tests for comment API endpoints."""

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
        json={"title": "Commented Doc", "content": "", "owner_id": str(owner_id)},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_add_comment(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Great document!"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Great document!"
    assert data["author_id"] == str(owner_id)
    assert data["document_id"] == doc_id


@pytest.mark.asyncio
async def test_add_comment_ignores_client_author_id(
    client: AsyncClient, owner_id: uuid.UUID
):
    doc_id = await _create_document(client, owner_id)

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "Spoofed author"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 201
    assert resp.json()["author_id"] == str(owner_id)


@pytest.mark.asyncio
async def test_add_comment_document_not_found(client: AsyncClient, owner_id: uuid.UUID):
    resp = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/comments",
        json={"content": "Orphan comment"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_comment_requires_auth(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Anonymous"},
    )
    assert resp.status_code == 401
    listed = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert listed.json() == []


@pytest.mark.asyncio
async def test_add_comment_denied_for_non_owner(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Not my document"},
        headers=_auth(uuid.uuid4()),
    )
    assert resp.status_code == 403
    listed = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert listed.json() == []


@pytest.mark.asyncio
async def test_list_comments(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    for i in range(3):
        await client.post(
            f"/api/v1/documents/{doc_id}/comments",
            json={"content": f"Comment {i}"},
            headers=_auth(owner_id),
        )

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_list_comments_requires_auth(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_comments_denied_for_non_owner(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)
    await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Private note"},
        headers=_auth(owner_id),
    )

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/comments", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_comments_document_not_found(client: AsyncClient, owner_id: uuid.UUID):
    resp = await client.get(
        f"/api/v1/documents/{uuid.uuid4()}/comments", headers=_auth(owner_id)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_comment(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "To delete"},
        headers=_auth(owner_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}", headers=_auth(owner_id)
    )
    assert resp.status_code == 204

    list_resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_comment_requires_auth(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)
    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Keep me"},
        headers=_auth(owner_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(f"/api/v1/documents/{doc_id}/comments/{comment_id}")
    assert resp.status_code == 401

    list_resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_delete_comment_denied_for_non_owner(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)
    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Keep me"},
        headers=_auth(owner_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}", headers=_auth(uuid.uuid4())
    )
    assert resp.status_code == 403

    list_resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_delete_comment_not_found(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}", headers=_auth(owner_id)
    )
    assert resp.status_code == 404
