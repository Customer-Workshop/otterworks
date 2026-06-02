"""Tests for the EventPublisher service."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.event_publisher import EventPublisher, _UUIDEncoder


class TestUUIDEncoder:
    def test_encodes_uuid(self):
        uid = uuid4()
        result = json.dumps({"id": uid}, cls=_UUIDEncoder)
        assert str(uid) in result

    def test_encodes_datetime(self):
        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = json.dumps({"ts": dt}, cls=_UUIDEncoder)
        assert "2024-01-15" in result

    def test_raises_for_unknown_type(self):
        with pytest.raises(TypeError):
            json.dumps({"bad": object()}, cls=_UUIDEncoder)

    def test_encodes_nested_uuids(self):
        data = {"owner": uuid4(), "items": [uuid4(), uuid4()]}
        result = json.dumps(data, cls=_UUIDEncoder)
        parsed = json.loads(result)
        assert isinstance(parsed["owner"], str)
        assert len(parsed["items"]) == 2


class TestEventPublisher:
    def test_init_creates_no_client(self):
        pub = EventPublisher()
        assert pub._client is None

    @patch("app.services.event_publisher.settings")
    def test_publish_skips_when_sns_disabled(self, mock_settings):
        mock_settings.sns_enabled = False
        pub = EventPublisher()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            pub.publish("document_created", {"id": str(uuid4())})
        )
        # No error, and no client was created
        assert pub._client is None

    @patch("app.services.event_publisher.settings")
    @patch("app.services.event_publisher.asyncio")
    def test_publish_sends_to_sns(self, mock_asyncio, mock_settings):
        mock_settings.sns_enabled = True
        mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:topic"
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_endpoint_url = None

        mock_client = MagicMock()
        pub = EventPublisher()
        pub._client = mock_client

        mock_asyncio.to_thread = AsyncMock()

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            pub.publish("document_updated", {"title": "Test"})
        )

        mock_asyncio.to_thread.assert_called_once()

    @patch("app.services.event_publisher.settings")
    def test_publish_handles_exception_gracefully(self, mock_settings):
        mock_settings.sns_enabled = True
        mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:topic"
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_endpoint_url = None

        pub = EventPublisher()
        mock_client = MagicMock()
        pub._client = mock_client

        import asyncio

        # Patch asyncio.to_thread to raise an exception
        with patch(
            "app.services.event_publisher.asyncio.to_thread",
            side_effect=Exception("SNS down"),
        ):
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                pub.publish("document_deleted", {"id": "abc"})
            )

    @patch("app.services.event_publisher.settings")
    def test_get_client_creates_boto3_client(self, mock_settings):
        mock_settings.aws_region = "us-west-2"
        mock_settings.aws_endpoint_url = "http://localhost:4566"

        pub = EventPublisher()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            client = pub._get_client()
            mock_boto3.client.assert_called_once_with(
                "sns",
                region_name="us-west-2",
                endpoint_url="http://localhost:4566",
            )
            assert client is not None

    @patch("app.services.event_publisher.settings")
    def test_get_client_without_endpoint(self, mock_settings):
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_endpoint_url = None

        pub = EventPublisher()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            pub._get_client()
            mock_boto3.client.assert_called_once_with(
                "sns",
                region_name="us-east-1",
            )

    @patch("app.services.event_publisher.settings")
    def test_get_client_caches(self, mock_settings):
        mock_settings.aws_region = "us-east-1"
        mock_settings.aws_endpoint_url = None

        pub = EventPublisher()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            c1 = pub._get_client()
            c2 = pub._get_client()
            assert c1 is c2
            mock_boto3.client.assert_called_once()
