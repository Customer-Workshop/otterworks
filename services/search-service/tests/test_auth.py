"""Tests for the search service authentication middleware.

These verify that the ``X-User-ID`` header is only trusted when accompanied
by a valid gateway HMAC signature, closing the header-spoofing attack path.
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest

from app.config import AppConfig, AuthConfig, MeiliSearchConfig, SQSConfig
from app.main import create_app

SIGNING_SECRET = "test-shared-secret"
SERVICE_TOKEN = "test-service-token"


def _sign(user_id: str, secret: str = SIGNING_SECRET) -> str:
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()


@pytest.fixture()
def secure_client(mock_meilisearch_client: MagicMock):
    """Flask test client with auth enabled and a gateway signing secret."""
    config = AppConfig(
        service_name="search-service-test",
        port=8087,
        debug=True,
        log_level="DEBUG",
        meilisearch=MeiliSearchConfig(
            url="http://localhost:7700",
            api_key="",
            documents_index="test-otterworks-documents",
            files_index="test-otterworks-files",
        ),
        sqs=SQSConfig(enabled=False),
        auth=AuthConfig(
            service_token=SERVICE_TOKEN,
            require_auth=True,
            gateway_signing_secret=SIGNING_SECRET,
        ),
    )
    with patch("app.services.meilisearch_client.meilisearch.Client") as mock_cls:
        mock_cls.return_value = mock_meilisearch_client
        flask_app = create_app(config)
        flask_app.config["TESTING"] = True
        yield flask_app.test_client()


class TestSpoofedHeaderRejected:
    def test_missing_identity_is_unauthorized(self, secure_client):
        resp = secure_client.get("/api/v1/search/?q=test")
        assert resp.status_code == 401

    def test_unsigned_user_id_is_rejected(self, secure_client):
        """A bare X-User-ID with no signature must not authenticate."""
        resp = secure_client.get("/api/v1/search/?q=test", headers={"X-User-ID": "victim"})
        assert resp.status_code == 401

    def test_bad_signature_is_rejected(self, secure_client):
        resp = secure_client.get(
            "/api/v1/search/?q=test",
            headers={"X-User-ID": "victim", "X-User-ID-Signature": "deadbeef"},
        )
        assert resp.status_code == 401

    def test_signature_for_other_user_is_rejected(self, secure_client):
        """A valid signature for one user cannot authorize another user id."""
        resp = secure_client.get(
            "/api/v1/search/?q=test",
            headers={"X-User-ID": "victim", "X-User-ID-Signature": _sign("attacker")},
        )
        assert resp.status_code == 401


class TestValidIdentityAccepted:
    def test_valid_signed_identity_is_accepted(self, secure_client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }
        resp = secure_client.get(
            "/api/v1/search/?q=test",
            headers={"X-User-ID": "user-1", "X-User-ID-Signature": _sign("user-1")},
        )
        assert resp.status_code == 200

    def test_service_token_is_accepted(self, secure_client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.return_value = {
            "estimatedTotalHits": 0,
            "hits": [],
        }
        resp = secure_client.get(
            "/api/v1/search/?q=test",
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_health_is_public(self, secure_client):
        resp = secure_client.get("/health")
        assert resp.status_code == 200
