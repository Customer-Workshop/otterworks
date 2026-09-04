"""Tests for document API endpoints."""

import os
import uuid

import jwt
import pytest
from httpx import AsyncClient

TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-pad32"  # noqa: S105
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)


def _make_jwt(user_id: str) -> str:
    return jwt.encode({"user_id": user_id}, TEST_JWT_SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_create_document(client: AsyncClient, owner_id: uuid.UUID):
    resp = await client.post(
        "/api/v1/documents/",
        json={
            "title": "Test Document",
            "content": "Hello world",
            "owner_id": str(owner_id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Document"
    assert data["content"] == "Hello world"
    assert data["word_count"] == 2
    assert data["version"] == 1
    assert data["owner_id"] == str(owner_id)


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Doc", "content": "Body", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, owner_id: uuid.UUID):
    for i in range(3):
        await client.post(
            "/api/v1/documents/",
            json={"title": f"Doc {i}", "content": "", "owner_id": str(owner_id)},
        )
    resp = await client.get("/api/v1/documents/", params={"owner_id": str(owner_id)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_documents_pagination(client: AsyncClient, owner_id: uuid.UUID):
    for i in range(5):
        await client.post(
            "/api/v1/documents/",
            json={"title": f"Doc {i}", "content": "", "owner_id": str(owner_id)},
        )
    resp = await client.get(
        "/api/v1/documents/", params={"owner_id": str(owner_id), "page": 1, "size": 2}
    )
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_update_document(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Original", "content": "Old body", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Updated", "content": "New body"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated"
    assert data["content"] == "New body"
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_patch_document(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Original", "content": "Body", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Patched Title"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Patched Title"
    assert data["content"] == "Body"  # unchanged
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "To Delete", "content": "", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_document_versions(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Versioned", "content": "v1", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    await client.put(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Versioned", "content": "v2"},
    )

    resp = await client.get(f"/api/v1/documents/{doc_id}/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1


@pytest.mark.asyncio
async def test_restore_version(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Restore Me", "content": "Original", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    await client.put(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Changed", "content": "Changed body"},
    )

    versions_resp = await client.get(f"/api/v1/documents/{doc_id}/versions")
    v1_id = versions_resp.json()[-1]["id"]  # first version

    resp = await client.post(f"/api/v1/documents/{doc_id}/versions/{v1_id}/restore")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Restore Me"
    assert data["content"] == "Original"
    assert data["version"] == 3


@pytest.mark.asyncio
async def test_search_documents(client: AsyncClient, owner_id: uuid.UUID):
    await client.post(
        "/api/v1/documents/",
        json={"title": "Python Guide", "content": "Learn Python", "owner_id": str(owner_id)},
    )
    await client.post(
        "/api/v1/documents/",
        json={"title": "Rust Guide", "content": "Learn Rust", "owner_id": str(owner_id)},
    )

    resp = await client.get("/api/v1/documents/search", params={"q": "Python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Guide"


@pytest.mark.asyncio
async def test_export_document_html(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Export", "content": "Content here", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/export", params={"format": "html"}
    )
    assert resp.status_code == 200
    assert "<h1>Export</h1>" in resp.text


@pytest.mark.asyncio
async def test_export_document_markdown(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Export MD", "content": "MD content", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/export", params={"format": "markdown"}
    )
    assert resp.status_code == 200
    assert "# Export MD" in resp.text


@pytest.mark.asyncio
async def test_create_document_via_jwt(anon_client: AsyncClient):
    """Create a document without owner_id in the body, using JWT instead."""
    user_id = uuid.uuid4()
    token = _make_jwt(str(user_id))
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "JWT Doc", "content": "Created via JWT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "JWT Doc"
    assert data["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_document_via_jwt_hs384(anon_client: AsyncClient):
    """Create a document using an HS384-signed JWT (matches auth-service algorithm)."""
    user_id = uuid.uuid4()
    token = jwt.encode({"sub": str(user_id)}, TEST_JWT_SECRET, algorithm="HS384")
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "HS384 Doc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_document_uses_x_user_id_header(anon_client: AsyncClient):
    """The gateway-injected X-User-ID header identifies the owner."""
    user_id = uuid.uuid4()
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "Header Doc"},
        headers={"X-User-ID": str(user_id)},
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_verified_token_outranks_the_x_user_id_header(anon_client: AsyncClient):
    """A token this service verified is the identity; a conflicting header is not."""
    token_user = uuid.uuid4()
    token = jwt.encode({"sub": str(token_user)}, TEST_JWT_SECRET, algorithm="HS384")

    agreeing = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "Agreeing"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-ID": str(token_user),
        },
    )
    assert agreeing.status_code == 201
    assert agreeing.json()["owner_id"] == str(token_user)

    conflicting = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "Conflicting"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-ID": str(uuid.uuid4()),
        },
    )
    assert conflicting.status_code == 401


@pytest.mark.asyncio
async def test_subjectless_token_does_not_fall_back_to_the_header(
    anon_client: AsyncClient,
):
    """A token that authenticates nobody must not let the header pick a victim."""
    token = jwt.encode({"scope": "documents"}, TEST_JWT_SECRET, algorithm="HS384")
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "Borrowed"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unverifiable_token_still_falls_back_to_the_header(
    anon_client: AsyncClient,
):
    """A token signed by someone else is not an identity claim this service can judge."""
    foreign = jwt.encode({"sub": str(uuid.uuid4())}, "another-secret", algorithm="HS256")
    user_id = uuid.uuid4()
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "Gateway Doc"},
        headers={
            "Authorization": f"Bearer {foreign}",
            "X-User-ID": str(user_id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_document_no_auth_returns_401(anon_client: AsyncClient):
    """Creating a document without owner_id and without auth returns 401."""
    resp = await anon_client.post(
        "/api/v1/documents/",
        json={"title": "No Auth Doc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_document_rejects_foreign_owner_id(
    client: AsyncClient, other_user_id: uuid.UUID
):
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Forged", "owner_id": str(other_user_id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_document_routes_reject_other_users(
    client: AsyncClient, other_client: AsyncClient, anon_client: AsyncClient
):
    created = await client.post(
        "/api/v1/documents/", json={"title": "Private", "content": "secret"}
    )
    doc_id = created.json()["id"]

    assert (await other_client.get(f"/api/v1/documents/{doc_id}")).status_code == 403
    assert (await anon_client.get(f"/api/v1/documents/{doc_id}")).status_code == 401
    assert (
        await other_client.put(
            f"/api/v1/documents/{doc_id}", json={"title": "Hijacked"}
        )
    ).status_code == 403
    assert (
        await other_client.patch(
            f"/api/v1/documents/{doc_id}", json={"title": "Hijacked"}
        )
    ).status_code == 403
    assert (await other_client.delete(f"/api/v1/documents/{doc_id}")).status_code == 403
    assert (
        await other_client.get(f"/api/v1/documents/{doc_id}/versions")
    ).status_code == 403
    assert (
        await other_client.get(f"/api/v1/documents/{doc_id}/export")
    ).status_code == 403
    assert (
        await other_client.post(f"/api/v1/documents/{doc_id}/share")
    ).status_code == 403


@pytest.mark.asyncio
async def test_search_only_returns_callers_documents(
    client: AsyncClient, other_client: AsyncClient, anon_client: AsyncClient
):
    await client.post(
        "/api/v1/documents/", json={"title": "Python Guide", "content": "Learn Python"}
    )

    mine = await client.get("/api/v1/documents/search", params={"q": "Python"})
    assert mine.status_code == 200
    assert mine.json()["total"] == 1

    theirs = await other_client.get("/api/v1/documents/search", params={"q": "Python"})
    assert theirs.status_code == 200
    assert theirs.json()["total"] == 0

    assert (
        await anon_client.get("/api/v1/documents/search", params={"q": "Python"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_list_rejects_foreign_owner_id_and_anonymous(
    client: AsyncClient,
    other_client: AsyncClient,
    anon_client: AsyncClient,
    owner_id: uuid.UUID,
):
    await client.post("/api/v1/documents/", json={"title": "Mine", "content": ""})

    spoofed = await other_client.get(
        "/api/v1/documents/", params={"owner_id": str(owner_id)}
    )
    assert spoofed.status_code == 403

    assert (await anon_client.get("/api/v1/documents/")).status_code == 401

    theirs = await other_client.get("/api/v1/documents/")
    assert theirs.status_code == 200
    assert theirs.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_from_template_stamps_caller(
    client: AsyncClient, other_client: AsyncClient, anon_client: AsyncClient,
    owner_id: uuid.UUID,
):
    template = await client.post(
        "/api/v1/templates/",
        json={"name": "T", "content": "body", "created_by": str(owner_id)},
    )
    template_id = template.json()["id"]
    path = f"/api/v1/documents/from-template/{template_id}"

    mine = await client.post(path, json={"title": "From Template"})
    assert mine.status_code == 201
    assert mine.json()["owner_id"] == str(owner_id)

    forged = await other_client.post(
        path, json={"title": "Forged", "owner_id": str(owner_id)}
    )
    assert forged.status_code == 403

    assert (await anon_client.post(path, json={"title": "Anon"})).status_code == 401
