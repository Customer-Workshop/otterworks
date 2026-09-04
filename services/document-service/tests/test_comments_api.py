"""Tests for comment API endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_comment(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Commented Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "Great document!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Great document!"
    # the author is the authenticated caller, never the body's author_id
    assert data["author_id"] == str(owner_id)
    assert data["document_id"] == doc_id


@pytest.mark.asyncio
async def test_add_comment_document_not_found(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "Orphan comment"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_comments(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    for i in range(3):
        await client.post(
            f"/api/v1/documents/{doc_id}/comments",
            json={"author_id": str(uuid.uuid4()), "content": f"Comment {i}"},
        )

    resp = await client.get(f"/api/v1/documents/{doc_id}/comments")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_delete_comment(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    comment_resp = await client.post(
        f"/api/v1/documents/{doc_id}/comments",
        json={"author_id": str(uuid.uuid4()), "content": "To delete"},
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(f"/api/v1/documents/{doc_id}/comments/{comment_id}")
    assert resp.status_code == 204

    list_resp = await client.get(f"/api/v1/documents/{doc_id}/comments")
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_comment_not_found(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}/comments/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_comments_reject_non_owner_and_anonymous(
    client: AsyncClient, other_client: AsyncClient, anon_client: AsyncClient
):
    doc_id = (
        await client.post("/api/v1/documents/", json={"title": "Doc", "content": ""})
    ).json()["id"]
    comment_id = (
        await client.post(
            f"/api/v1/documents/{doc_id}/comments", json={"content": "Mine"}
        )
    ).json()["id"]
    comments_path = f"/api/v1/documents/{doc_id}/comments"

    assert (
        await other_client.post(comments_path, json={"content": "Intruder"})
    ).status_code == 403
    assert (
        await anon_client.post(comments_path, json={"content": "Anon"})
    ).status_code == 401

    assert (await other_client.get(comments_path)).status_code == 403
    assert (await anon_client.get(comments_path)).status_code == 401

    assert (
        await other_client.delete(f"{comments_path}/{comment_id}")
    ).status_code == 403
    assert (await anon_client.delete(f"{comments_path}/{comment_id}")).status_code == 401

    # the document owner can still delete the comment
    assert (await client.delete(f"{comments_path}/{comment_id}")).status_code == 204
