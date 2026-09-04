"""Object-level authorization tests for the indexing API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import meilisearch
import pytest
from requests import Response

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app

SERVICE_TOKEN = "internal-service-token"
OWNER = "user-owner"
ATTACKER = "user-attacker"


def _not_indexed() -> meilisearch.errors.MeilisearchApiError:
    return meilisearch.errors.MeilisearchApiError("document not found", Response())


@pytest.fixture()
def secured_config(app_config: AppConfig) -> AppConfig:
    """App config with authentication and authorization enforced."""
    return AppConfig(
        service_name=app_config.service_name,
        port=app_config.port,
        debug=app_config.debug,
        log_level=app_config.log_level,
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-otterworks-documents",
            files_index="test-otterworks-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(service_token=SERVICE_TOKEN, require_auth=True),
    )


@pytest.fixture()
def secured_client(secured_config: AppConfig, mock_meilisearch_client: MagicMock):
    """Test client for an app that enforces ownership."""
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        flask_app = create_app(secured_config)
        flask_app.config["TESTING"] = True
        yield flask_app.test_client()


@pytest.fixture()
def indexed_record(mock_meilisearch_client: MagicMock) -> MagicMock:
    """Make the index return a record owned by OWNER."""
    mock_index = mock_meilisearch_client.index.return_value
    mock_index.get_document.return_value = {"id": "doc-123", "owner_id": OWNER}
    return mock_index


class TestDeleteFromIndexOwnership:
    """DELETE /api/v1/search/index/{type}/{id}."""

    def test_owner_can_delete(self, secured_client, indexed_record):
        response = secured_client.delete(
            "/api/v1/search/index/document/doc-123",
            headers={"X-User-ID": OWNER},
        )
        assert response.status_code == 200
        assert response.get_json()["status"] == "deleted"

    def test_other_user_is_forbidden(self, secured_client, indexed_record):
        response = secured_client.delete(
            "/api/v1/search/index/document/doc-123",
            headers={"X-User-ID": ATTACKER},
        )
        assert response.status_code == 403
        indexed_record.delete_document.assert_not_called()

    def test_missing_user_id_is_unauthorized(self, secured_client, indexed_record):
        response = secured_client.delete("/api/v1/search/index/document/doc-123")
        assert response.status_code == 401
        indexed_record.delete_document.assert_not_called()

    def test_service_token_can_delete_any_record(self, secured_client, indexed_record):
        response = secured_client.delete(
            "/api/v1/search/index/file/file-123",
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        )
        assert response.status_code == 200

    def test_unindexed_record_is_not_found(self, secured_client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.get_document.side_effect = _not_indexed()
        response = secured_client.delete(
            "/api/v1/search/index/document/doc-missing",
            headers={"X-User-ID": OWNER},
        )
        assert response.status_code == 404


class TestIndexDocumentOwnership:
    """POST /api/v1/search/index/document."""

    def test_owner_can_reindex_own_document(self, secured_client, indexed_record):
        response = secured_client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-123", "title": "Mine", "owner_id": OWNER},
            headers={"X-User-ID": OWNER},
        )
        assert response.status_code == 201

    def test_other_user_cannot_overwrite(self, secured_client, indexed_record):
        response = secured_client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-123", "title": "Stolen", "owner_id": ATTACKER},
            headers={"X-User-ID": ATTACKER},
        )
        assert response.status_code == 403
        indexed_record.add_documents.assert_not_called()

    def test_missing_user_id_is_unauthorized(self, secured_client, indexed_record):
        response = secured_client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-123", "title": "Stolen"},
        )
        assert response.status_code == 401
        indexed_record.add_documents.assert_not_called()

    def test_owner_id_is_forced_to_caller(self, secured_client, mock_meilisearch_client):
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.get_document.side_effect = _not_indexed()
        response = secured_client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-new", "title": "Planted", "owner_id": OWNER},
            headers={"X-User-ID": ATTACKER},
        )
        assert response.status_code == 201
        indexed = mock_index.add_documents.call_args[0][0][0]
        assert indexed["owner_id"] == ATTACKER

    def test_service_token_keeps_payload_owner(self, secured_client, mock_meilisearch_client):
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.get_document.side_effect = _not_indexed()
        response = secured_client.post(
            "/api/v1/search/index/document",
            json={"id": "doc-new", "title": "From document-service", "owner_id": OWNER},
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        )
        assert response.status_code == 201
        indexed = mock_index.add_documents.call_args[0][0][0]
        assert indexed["owner_id"] == OWNER


class TestIndexFileOwnership:
    """POST /api/v1/search/index/file."""

    def test_owner_can_reindex_own_file(self, secured_client, indexed_record):
        indexed_record.get_document.return_value = {"id": "file-123", "owner_id": OWNER}
        response = secured_client.post(
            "/api/v1/search/index/file",
            json={"id": "file-123", "name": "mine.pdf", "owner_id": OWNER},
            headers={"X-User-ID": OWNER},
        )
        assert response.status_code == 201

    def test_other_user_cannot_overwrite(self, secured_client, indexed_record):
        indexed_record.get_document.return_value = {"id": "file-123", "owner_id": OWNER}
        response = secured_client.post(
            "/api/v1/search/index/file",
            json={"id": "file-123", "name": "stolen.pdf", "owner_id": ATTACKER},
            headers={"X-User-ID": ATTACKER},
        )
        assert response.status_code == 403
        indexed_record.add_documents.assert_not_called()

    def test_missing_user_id_is_unauthorized(self, secured_client, indexed_record):
        response = secured_client.post(
            "/api/v1/search/index/file",
            json={"id": "file-123", "name": "stolen.pdf"},
        )
        assert response.status_code == 401
        indexed_record.add_documents.assert_not_called()

    def test_owner_id_is_forced_to_caller(self, secured_client, mock_meilisearch_client):
        mock_index = mock_meilisearch_client.index.return_value
        mock_index.get_document.side_effect = _not_indexed()
        response = secured_client.post(
            "/api/v1/search/index/file",
            json={"id": "file-new", "name": "planted.pdf", "owner_id": OWNER},
            headers={"X-User-ID": ATTACKER},
        )
        assert response.status_code == 201
        indexed = mock_index.add_documents.call_args[0][0][0]
        assert indexed["owner_id"] == ATTACKER


class TestReindexAuthorization:
    """POST /api/v1/search/reindex is an internal-only operation."""

    def test_regular_user_is_forbidden(self, secured_client):
        response = secured_client.post("/api/v1/search/reindex", headers={"X-User-ID": OWNER})
        assert response.status_code == 403

    def test_missing_user_id_is_unauthorized(self, secured_client):
        response = secured_client.post("/api/v1/search/reindex")
        assert response.status_code == 401

    def test_service_token_can_reindex(self, secured_client):
        with patch("app.services.indexer.Indexer._fetch_all_documents", return_value=[]), patch(
            "app.services.indexer.Indexer._fetch_all_files", return_value=[]
        ):
            response = secured_client.post(
                "/api/v1/search/reindex",
                headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
            )
        assert response.status_code == 200
