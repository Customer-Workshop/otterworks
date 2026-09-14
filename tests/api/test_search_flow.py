import pytest
import uuid


pytestmark = pytest.mark.api_flow


def test_search_query_suggest_and_advanced_flow(api_client):
    user = api_client.register_user("search-flow")

    search_response = api_client.client.get(
        "/api/v1/search/",
        headers=user.auth_headers,
        params={"q": "unique searchable", "owner_id": user.id, "page": 1, "size": 10},
    )
    assert search_response.status_code == 200, search_response.text
    search_data = search_response.json()
    assert "results" in search_data
    assert "total" in search_data

    suggest_response = api_client.client.get(
        "/api/v1/search/suggest",
        headers=user.auth_headers,
        params={"q": "un"},
    )
    assert suggest_response.status_code == 200, suggest_response.text
    assert "suggestions" in suggest_response.json()

    advanced_response = api_client.client.post(
        "/api/v1/search/advanced",
        headers=user.auth_headers,
        json={"q": "otterworks", "owner_id": user.id, "page": 1, "size": 10},
    )
    assert advanced_response.status_code == 200, advanced_response.text


def test_index_endpoints_reject_end_user_tokens(api_client):
    """Indexing is internal: a user JWT must not be able to write to or wipe the index."""
    user = api_client.register_user("search-index-user")
    document_id = str(uuid.uuid4())

    index_response = api_client.client.post(
        "/api/v1/search/index/document",
        headers=user.auth_headers,
        json={
            "id": document_id,
            "title": f"Not Indexable {api_client.run_id}",
            "content": "otterworks content",
            "owner_id": user.id,
            "type": "document",
        },
    )
    assert index_response.status_code == 403, index_response.text

    delete_response = api_client.client.delete(
        f"/api/v1/search/index/document/{document_id}",
        headers=user.auth_headers,
    )
    assert delete_response.status_code == 403, delete_response.text

    reindex_response = api_client.client.post("/api/v1/search/reindex", headers=user.auth_headers)
    assert reindex_response.status_code == 403, reindex_response.text


def test_search_rejects_forged_identity_without_token(api_client):
    """X-User-ID alone is not an identity; the gateway requires a JWT and the service ignores the header."""
    user = api_client.register_user("search-forged-identity")
    response = api_client.client.get(
        "/api/v1/search/",
        headers={"X-User-ID": user.id},
        params={"q": "otterworks"},
    )
    assert response.status_code == 401, response.text
