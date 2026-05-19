"""Tests for EventPublisher — event publishing, error handling, retry logic."""

import json
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.services.event_publisher import EventPublisher, _UUIDEncoder


class TestUUIDEncoder:
    def test_encodes_uuid(self):
        uid = UUID("12345678-1234-5678-1234-567812345678")
        result = json.dumps({"id": uid}, cls=_UUIDEncoder)
        assert '"12345678-1234-5678-1234-567812345678"' in result

    def test_encodes_datetime(self):
        from datetime import UTC, datetime

        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = json.dumps({"ts": dt}, cls=_UUIDEncoder)
        assert "2025-01-15" in result

    def test_raises_for_unknown_type(self):
        with pytest.raises(TypeError):
            json.dumps({"obj": object()}, cls=_UUIDEncoder)


class TestEventPublisher:
    def test_init_creates_null_client(self):
        pub = EventPublisher()
        assert pub._client is None

    @pytest.mark.asyncio
    async def test_publish_skips_when_disabled(self):
        pub = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = False
            await pub.publish("test_event", {"key": "value"})
        assert pub._client is None

    @pytest.mark.asyncio
    async def test_publish_sends_to_sns(self):
        pub = EventPublisher()
        mock_client = MagicMock()
        mock_client.publish = MagicMock()
        pub._client = mock_client

        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:test-topic"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            with patch("asyncio.to_thread") as mock_thread:
                mock_thread.return_value = None
                await pub.publish("document_created", {"doc_id": "abc"})
                mock_thread.assert_called_once()
                call_args = mock_thread.call_args
                assert call_args[0][0] == mock_client.publish
                assert call_args[1]["TopicArn"] == "arn:aws:sns:us-east-1:123:test-topic"

    @pytest.mark.asyncio
    async def test_publish_handles_exception(self):
        pub = EventPublisher()
        mock_client = MagicMock()
        pub._client = mock_client

        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:test-topic"

            with patch("asyncio.to_thread", side_effect=Exception("SNS error")):
                # Should not raise
                await pub.publish("test_event", {"key": "value"})

    def test_get_client_creates_boto3_client(self):
        pub = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = "http://localhost:4566"
            with patch("boto3.client") as mock_boto:
                mock_boto.return_value = MagicMock()
                client = pub._get_client()
                mock_boto.assert_called_once_with(
                    "sns",
                    region_name="us-east-1",
                    endpoint_url="http://localhost:4566",
                )
                assert client is not None

    def test_get_client_caches_instance(self):
        pub = EventPublisher()
        mock = MagicMock()
        pub._client = mock
        assert pub._get_client() is mock
