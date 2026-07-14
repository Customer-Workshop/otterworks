"""Tests for sample item API endpoints."""

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
async def test_create_item(client: AsyncClient, owner_id: uuid.UUID):
    resp = await client.post(
        "/api/v1/samples/",
        json={
            "name": "Test Item",
            "description": "Hello world",
            "owner_id": str(owner_id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Item"
    assert data["description"] == "Hello world"
    assert data["owner_id"] == str(owner_id)
    assert data["is_deleted"] is False


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient, owner_id: uuid.UUID):
    token = _make_jwt(str(owner_id))
    create_resp = await client.post(
        "/api/v1/samples/",
        json={"name": "Item", "description": "Body", "owner_id": str(owner_id)},
    )
    item_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/samples/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == item_id


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient, owner_id: uuid.UUID):
    token = _make_jwt(str(owner_id))
    resp = await client.get(
        f"/api/v1/samples/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_item_wrong_owner_forbidden(client: AsyncClient, owner_id: uuid.UUID):
    create_resp = await client.post(
        "/api/v1/samples/",
        json={"name": "Item", "owner_id": str(owner_id)},
    )
    item_id = create_resp.json()["id"]

    other_token = _make_jwt(str(uuid.uuid4()))
    resp = await client.get(
        f"/api/v1/samples/{item_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_items(client: AsyncClient, owner_id: uuid.UUID):
    for i in range(3):
        await client.post(
            "/api/v1/samples/",
            json={"name": f"Item {i}", "owner_id": str(owner_id)},
        )
    resp = await client.get("/api/v1/samples/", params={"owner_id": str(owner_id)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_items_pagination(client: AsyncClient, owner_id: uuid.UUID):
    for i in range(5):
        await client.post(
            "/api/v1/samples/",
            json={"name": f"Item {i}", "owner_id": str(owner_id)},
        )
    resp = await client.get(
        "/api/v1/samples/", params={"owner_id": str(owner_id), "page": 1, "size": 2}
    )
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient, owner_id: uuid.UUID):
    token = _make_jwt(str(owner_id))
    create_resp = await client.post(
        "/api/v1/samples/",
        json={"name": "Original", "description": "Old", "owner_id": str(owner_id)},
    )
    item_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/samples/{item_id}",
        json={"name": "Updated", "description": "New"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["description"] == "New"


@pytest.mark.asyncio
async def test_patch_item(client: AsyncClient, owner_id: uuid.UUID):
    token = _make_jwt(str(owner_id))
    create_resp = await client.post(
        "/api/v1/samples/",
        json={"name": "Original", "description": "Body", "owner_id": str(owner_id)},
    )
    item_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/samples/{item_id}",
        json={"name": "Patched"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Patched"
    assert data["description"] == "Body"  # unchanged


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient, owner_id: uuid.UUID):
    token = _make_jwt(str(owner_id))
    create_resp = await client.post(
        "/api/v1/samples/",
        json={"name": "To Delete", "owner_id": str(owner_id)},
    )
    item_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/samples/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    resp = await client.get(
        f"/api/v1/samples/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_item_via_jwt(client: AsyncClient):
    """Create an item without owner_id in the body, using JWT instead."""
    user_id = uuid.uuid4()
    token = _make_jwt(str(user_id))
    resp = await client.post(
        "/api/v1/samples/",
        json={"name": "JWT Item"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "JWT Item"
    assert data["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_item_via_jwt_hs384(client: AsyncClient):
    """Create an item using an HS384-signed JWT (matches auth-service algorithm)."""
    user_id = uuid.uuid4()
    token = jwt.encode({"sub": str(user_id)}, TEST_JWT_SECRET, algorithm="HS384")
    resp = await client.post(
        "/api/v1/samples/",
        json={"name": "HS384 Item"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_item_x_user_id_header_ignored(client: AsyncClient):
    """X-User-Id header alone is not trusted (prevents identity spoofing)."""
    user_id = uuid.uuid4()
    resp = await client.post(
        "/api/v1/samples/",
        json={"name": "Header Item"},
        headers={"X-User-Id": str(user_id)},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_item_no_auth_returns_401(client: AsyncClient):
    """Creating an item without owner_id and without auth returns 401."""
    resp = await client.post(
        "/api/v1/samples/",
        json={"name": "No Auth Item"},
    )
    assert resp.status_code == 401
