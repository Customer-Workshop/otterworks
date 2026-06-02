"""Tests for the EventPublisher SNS integration."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.event_publisher import EventPublisher, _UUIDEncoder


class TestUUIDEncoder:
    def test_encodes_uuid(self):
        uid = uuid4()
        result = json.dumps({"id": uid}, cls=_UUIDEncoder)
        assert str(uid) in result

    def test_encodes_datetime(self):
        dt = datetime(2024, 1, 15, 12, 30, 0)
        result = json.dumps({"ts": dt}, cls=_UUIDEncoder)
        assert "2024-01-15" in result

    def test_encodes_string_unchanged(self):
        result = json.dumps({"name": "test"}, cls=_UUIDEncoder)
        parsed = json.loads(result)
        assert parsed["name"] == "test"

    def test_raises_for_unsupported_type(self):
        with pytest.raises(TypeError):
            json.dumps({"obj": object()}, cls=_UUIDEncoder)


class TestEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_skips_when_disabled(self):
        publisher = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = False
            await publisher.publish("test_event", {"id": "123"})
            # No error and no SNS call

    @pytest.mark.asyncio
    async def test_publish_sends_to_sns(self):
        publisher = EventPublisher()
        mock_client = MagicMock()
        mock_client.publish = MagicMock()

        with patch("app.services.event_publisher.settings") as mock_settings, \
             patch.object(publisher, "_get_client", return_value=mock_client), \
             patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:topic"

            await publisher.publish("document_created", {"id": "doc-1"})

            mock_to_thread.assert_called_once()
            call_args = mock_to_thread.call_args
            assert call_args[0][0] == mock_client.publish
            assert call_args[1]["TopicArn"] == "arn:aws:sns:us-east-1:123:topic"

            message_body = json.loads(call_args[1]["Message"])
            assert message_body["event_type"] == "document_created"
            assert message_body["payload"]["id"] == "doc-1"
            assert "timestamp" in message_body

            assert call_args[1]["MessageAttributes"]["event_type"]["StringValue"] == "document_created"

    @pytest.mark.asyncio
    async def test_publish_handles_exception_gracefully(self):
        publisher = EventPublisher()
        mock_client = MagicMock()

        with patch("app.services.event_publisher.settings") as mock_settings, \
             patch.object(publisher, "_get_client", return_value=mock_client), \
             patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123:topic"
            mock_to_thread.side_effect = Exception("SNS error")

            # Should not raise
            await publisher.publish("test_event", {"id": "123"})

    def test_get_client_creates_boto3_client(self):
        publisher = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings, \
             patch("boto3.client") as mock_boto:
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            client = publisher._get_client()
            mock_boto.assert_called_once_with("sns", region_name="us-east-1")

    def test_get_client_with_endpoint_url(self):
        publisher = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings, \
             patch("boto3.client") as mock_boto:
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = "http://localhost:4566"

            client = publisher._get_client()
            mock_boto.assert_called_once_with(
                "sns",
                region_name="us-east-1",
                endpoint_url="http://localhost:4566",
            )

    def test_get_client_caches(self):
        publisher = EventPublisher()
        with patch("app.services.event_publisher.settings") as mock_settings, \
             patch("boto3.client") as mock_boto:
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            client1 = publisher._get_client()
            client2 = publisher._get_client()
            mock_boto.assert_called_once()
            assert client1 is client2
