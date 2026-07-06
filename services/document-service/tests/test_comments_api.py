"""Tests for comment API endpoints."""

import os
import uuid

import jwt
import pytest
from httpx import AsyncClient

TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-pad32"  # noqa: S105
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


def _make_jwt(user_id: str) -> str:
    return jwt.encode({"user_id": user_id}, TEST_JWT_SECRET, algorithm="HS256")


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_jwt(str(user_id))}"}


@pytest.mark.asyncio
async def test_add_comment(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Commented Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]
    author_id = uuid.uuid4()

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Great document!"},
        headers=_auth_headers(author_id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Great document!"
    assert data["author_id"] == str(author_id)
    assert data["document_id"] == doc_id


@pytest.mark.asyncio
async def test_add_comment_no_auth(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Should fail"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_add_comment_document_not_found(client: AsyncClient):
    user_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/comments",
        json={"content": "Orphan comment"},
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_comments(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]
    user_id = uuid.uuid4()

    for i in range(3):
        await client.post(
            f"/api/v1/documents/{doc_id}/comments",
            json={"content": f"Comment {i}"},
            headers=_auth_headers(user_id),
        )

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/comments",
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_list_comments_no_auth(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_comment(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]
    author_id = uuid.uuid4()

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "To delete"},
        headers=_auth_headers(author_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}",
        headers=_auth_headers(author_id),
    )
    assert resp.status_code == 204

    list_resp = await client.get(
        f"/api/v1/documents/{doc_id}/comments",
        headers=_auth_headers(author_id),
    )
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_comment_forbidden(client: AsyncClient, owner_id: uuid.UUID):
    """Another user cannot delete someone else's comment."""
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]
    author_id = uuid.uuid4()
    other_user = uuid.uuid4()

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"content": "Not yours"},
        headers=_auth_headers(author_id),
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{comment_id}",
        headers=_auth_headers(other_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_comment_no_auth(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}"
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_comment_not_found(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]
    user_id = uuid.uuid4()

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}",
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 404
