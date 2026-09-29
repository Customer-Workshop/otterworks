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
async def test_create_document_via_jwt(client: AsyncClient):
    """Create a document without owner_id in the body, using JWT instead."""
    user_id = uuid.uuid4()
    token = _make_jwt(str(user_id))
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "JWT Doc", "content": "Created via JWT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "JWT Doc"
    assert data["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_document_via_jwt_hs384(client: AsyncClient):
    """Create a document using an HS384-signed JWT (matches auth-service algorithm)."""
    user_id = uuid.uuid4()
    token = jwt.encode({"sub": str(user_id)}, TEST_JWT_SECRET, algorithm="HS384")
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "HS384 Doc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_document_x_user_id_header_ignored(client: AsyncClient):
    """X-User-Id header alone is not trusted (prevents identity spoofing)."""
    user_id = uuid.uuid4()
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Header Doc"},
        headers={"X-User-Id": str(user_id)},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_document_no_auth_returns_401(client: AsyncClient):
    """Creating a document without owner_id and without auth returns 401."""
    resp = await client.post(
        "/api/v1/documents/",
        json={"title": "No Auth Doc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hs512_jwt_authenticates_document_endpoints(client: AsyncClient):
    user_id = uuid.uuid4()
    token = jwt.encode({"sub": str(user_id)}, TEST_JWT_SECRET, algorithm="HS512")
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "HS512 Document", "content": "Exportable content"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    document = create_resp.json()
    assert document["owner_id"] == str(user_id)
    doc_id = document["id"]

    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert get_resp.status_code == 200

    update_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"title": "Updated HS512 Document"},
        headers=headers,
    )
    assert update_resp.status_code == 200

    for export_format in ("markdown", "html", "pdf"):
        export_resp = await client.get(
            f"/api/v1/documents/{doc_id}/export",
            params={"format": export_format},
            headers=headers,
        )
        assert export_resp.status_code == 200

    delete_resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_unverifiable_jwt_uses_gateway_user_id(client: AsyncClient):
    user_id = uuid.uuid4()
    token = jwt.encode(
        {"sub": str(user_id)},
        "some-other-deployment-secret-000000",
        algorithm="HS256",
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-User-ID": str(user_id),
    }
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Gateway Identity Document"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    document = create_resp.json()
    assert document["owner_id"] == str(user_id)

    get_resp = await client.get(f"/api/v1/documents/{document['id']}", headers=headers)
    assert get_resp.status_code == 200

    export_resp = await client.get(
        f"/api/v1/documents/{document['id']}/export",
        params={"format": "markdown"},
        headers=headers,
    )
    assert export_resp.status_code == 200


@pytest.mark.asyncio
async def test_unverifiable_jwt_without_gateway_identity_returns_401(
    client: AsyncClient, owner_id: uuid.UUID
):
    token = jwt.encode(
        {"sub": str(owner_id)},
        "some-other-deployment-secret-000000",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Unverified JWT Document"},
        headers=headers,
    )
    assert create_resp.status_code == 401

    existing_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Existing Document", "owner_id": str(owner_id)},
    )
    export_resp = await client.get(
        f"/api/v1/documents/{existing_resp.json()['id']}/export",
        headers=headers,
    )
    assert export_resp.status_code == 401


@pytest.mark.asyncio
async def test_document_export_without_identity_returns_401(
    client: AsyncClient, owner_id: uuid.UUID
):
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Existing Document", "owner_id": str(owner_id)},
    )

    export_resp = await client.get(f"/api/v1/documents/{create_resp.json()['id']}/export")
    assert export_resp.status_code == 401


@pytest.mark.asyncio
async def test_document_owner_checks_with_jwt_and_gateway_identity(
    client: AsyncClient, owner_id: uuid.UUID
):
    other_user_id = uuid.uuid4()
    create_resp = await client.post(
        "/api/v1/documents/",
        json={"title": "Owner Checked Document", "owner_id": str(owner_id)},
    )
    doc_id = create_resp.json()["id"]

    valid_token = _make_jwt(str(other_user_id))
    valid_headers = {"Authorization": f"Bearer {valid_token}"}
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=valid_headers)
    assert get_resp.status_code == 403
    export_resp = await client.get(f"/api/v1/documents/{doc_id}/export", headers=valid_headers)
    assert export_resp.status_code == 403

    unverifiable_token = jwt.encode(
        {"sub": str(other_user_id)},
        "some-other-deployment-secret-000000",
        algorithm="HS256",
    )
    gateway_headers = {
        "Authorization": f"Bearer {unverifiable_token}",
        "X-User-ID": str(other_user_id),
    }
    gateway_get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=gateway_headers)
    assert gateway_get_resp.status_code == 403
