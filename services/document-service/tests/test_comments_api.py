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


async def _create_document(client: AsyncClient, owner_id: uuid.UUID, title: str = "Doc") -> str:
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": title, "content": "", "owner_id": str(owner_id)},
    )
    return create_resp.json()["id"]


@pytest.mark.asyncio
async def test_add_comment(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id, "Commented Doc")
    author_id = str(uuid.uuid4())

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": author_id, "content": "Great document!"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Great document!"
    assert data["author_id"] == author_id
    assert data["document_id"] == doc_id


@pytest.mark.asyncio
async def test_add_comment_document_not_found(client: AsyncClient, owner_id: uuid.UUID):
    resp = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "Orphan comment"},
        headers=_auth(owner_id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_comments(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    for i in range(3):
        await client.post(
            f"/api/v1/documents/{doc_id}/comments",
            json={"author_id": str(uuid.uuid4()), "content": f"Comment {i}"},
            headers=_auth(owner_id),
        )

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id))
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_delete_comment(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "To delete"},
        headers=_auth(owner_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}", headers=_auth(owner_id)
    )
    assert resp.status_code == 204

    list_resp = await client.get(
        f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id)
    )
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_comment_not_found(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}", headers=_auth(owner_id)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_comment_endpoints_require_auth(client: AsyncClient, owner_id: uuid.UUID):
    doc_id = await _create_document(client, owner_id)

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(owner_id), "content": "anon"},
    )
    assert resp.status_code == 401
    resp = await client.get(f"/api/v1/documents/{doc_id}/comments")
    assert resp.status_code == 401
    resp = await client.delete(f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_comment_endpoints_reject_non_owner(client: AsyncClient, owner_id: uuid.UUID):
    """Another authenticated user cannot read, add, or delete comments on the document."""
    attacker_id = uuid.uuid4()
    doc_id = await _create_document(client, owner_id, "Victim Doc")

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(owner_id), "content": "private"},
        headers=_auth(owner_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments", headers=_auth(attacker_id))
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(attacker_id), "content": "tamper"},
        headers=_auth(attacker_id),
    )
    assert resp.status_code == 403

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}", headers=_auth(attacker_id)
    )
    assert resp.status_code == 403

    # The owner still sees exactly the original comment.
    list_resp = await client.get(
        f"/api/v1/documents/{doc_id}/comments", headers=_auth(owner_id)
    )
    assert [c["id"] for c in list_resp.json()] == [comment_id]
