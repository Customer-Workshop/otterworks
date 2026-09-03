"""Tests for indexing API endpoints."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from app.main import create_app


@pytest.fixture()
def unconfigured_app(app_config, mock_meilisearch_client):
    """Create an app without a configured service token."""
    config = replace(app_config, auth=replace(app_config.auth, service_token=""))
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        flask_app = create_app(config)
        flask_app.config["TESTING"] = True
        yield flask_app


class TestIndexDocumentEndpoint:
    """Tests for POST /api/v1/search/index/document."""

    def test_index_document_success(self, client, mock_meilisearch_client, service_headers):
        """Index a valid document returns 201."""
        response = client.post(
            "/api/v1/search/index/document",
            json={
                "id": "doc-123",
                "title": "My Document",
                "content": "Document body text",
                "owner_id": "user-1",
                "tags": ["work"],
            },
            headers=service_headers,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "indexed"
        assert data["id"] == "doc-123"
        assert data["type"] == "document"

    def test_index_document_missing_body(self, client, service_headers):
        """Index with empty body returns 400."""
        response = client.post(
            "/api/v1/search/index/document",
            content_type="application/json",
            headers=service_headers,
        )
        assert response.status_code == 400

    def test_index_document_missing_id(self, client, mock_meilisearch_client, service_headers):
        """Index document without id returns 400."""
        response = client.post(
            "/api/v1/search/index/document",
            json={"title": "No ID Doc"},
            headers=service_headers,
        )
        assert response.status_code == 400

    def test_index_document_missing_title(self, client, mock_meilisearch_client, service_headers):
        """Index document without title returns 400."""
        response = client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-no-title"},
            headers=service_headers,
        )
        assert response.status_code == 400


class TestIndexFileEndpoint:
    """Tests for POST /api/v1/search/index/file."""

    def test_index_file_success(self, client, mock_meilisearch_client, service_headers):
        """Index a valid file returns 201."""
        response = client.post(
            "/api/v1/search/index/file",
            json={
                "id": "file-123",
                "name": "report.pdf",
                "mime_type": "application/pdf",
                "owner_id": "user-1",
                "folder_id": "folder-1",
                "tags": ["report"],
                "size": 1024,
            },
            headers=service_headers,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "indexed"
        assert data["id"] == "file-123"
        assert data["type"] == "file"

    def test_index_file_missing_name(self, client, mock_meilisearch_client, service_headers):
        """Index file without name returns 400."""
        response = client.post(
            "/api/v1/search/index/file",
            json={"id": "file-no-name"},
            headers=service_headers,
        )
        assert response.status_code == 400


class TestDeleteFromIndexEndpoint:
    """Tests for DELETE /api/v1/search/index/{type}/{id}."""

    def test_delete_document(self, client, mock_meilisearch_client, service_headers):
        """Delete a document from index returns 200."""
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.get_document.return_value = {"id": "doc-123"}
        response = client.delete(
            "/api/v1/search/index/document/doc-123",
            headers=service_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "deleted"

    def test_delete_invalid_type(self, client, mock_meilisearch_client, service_headers):
        """Delete with invalid type returns 400."""
        response = client.delete(
            "/api/v1/search/index/invalid/doc-123",
            headers=service_headers,
        )
        assert response.status_code == 400


class TestReindexEndpoint:
    """Tests for POST /api/v1/search/reindex."""

    def test_reindex_success(self, client, mock_meilisearch_client, service_headers):
        """Reindex returns 200."""
        response = client.post(
            "/api/v1/search/reindex",
            headers=service_headers,
            json={},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "reindexed"


INDEX_ENDPOINTS = [
    ("post", "/api/v1/search/index/document", {"id": "doc-123", "title": "Document"}),
    ("post", "/api/v1/search/index/file", {"id": "file-123", "name": "file.txt"}),
    ("delete", "/api/v1/search/index/document/doc-123", None),
    ("post", "/api/v1/search/reindex", {}),
]


class TestIndexEndpointsRequireServiceToken:
    """Tests for service-token protection on index endpoints."""

    @pytest.mark.parametrize("method,path,json_body", INDEX_ENDPOINTS)
    def test_missing_token_rejected_even_with_user_id(
        self,
        client,
        mock_meilisearch_client,
        method,
        path,
        json_body,
    ):
        """Index endpoints reject gateway identity without a service token."""
        request_method = getattr(client, method)
        kwargs = {"headers": {"X-User-ID": "attacker"}}
        if json_body is not None:
            kwargs["json"] = json_body

        response = request_method(path, **kwargs)

        assert response.status_code == 401
        mock_meilisearch_client.index.return_value.add_documents.assert_not_called()
        mock_meilisearch_client.index.return_value.delete_document.assert_not_called()

    @pytest.mark.parametrize("method,path,json_body", INDEX_ENDPOINTS)
    def test_invalid_token_rejected_even_with_user_id(
        self,
        client,
        mock_meilisearch_client,
        method,
        path,
        json_body,
    ):
        """Index endpoints reject an invalid service token and gateway identity."""
        request_method = getattr(client, method)
        kwargs = {
            "headers": {
                "Authorization": "Bearer wrong-token",
                "X-User-ID": "attacker",
            }
        }
        if json_body is not None:
            kwargs["json"] = json_body

        response = request_method(path, **kwargs)

        assert response.status_code == 401
        mock_meilisearch_client.index.return_value.add_documents.assert_not_called()
        mock_meilisearch_client.index.return_value.delete_document.assert_not_called()

    @pytest.mark.parametrize("method,path,json_body", INDEX_ENDPOINTS)
    def test_missing_configuration_forbidden(
        self,
        unconfigured_app,
        mock_meilisearch_client,
        method,
        path,
        json_body,
    ):
        """Index endpoints return forbidden when no service token is configured."""
        request_method = getattr(unconfigured_app.test_client(), method)
        kwargs = {"headers": {"Authorization": "Bearer test-service-token"}}
        if json_body is not None:
            kwargs["json"] = json_body

        response = request_method(path, **kwargs)

        assert response.status_code == 403
        mock_meilisearch_client.index.return_value.add_documents.assert_not_called()
        mock_meilisearch_client.index.return_value.delete_document.assert_not_called()
