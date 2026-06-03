"""Tests for the EventPublisher service."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.event_publisher import EventPublisher, _UUIDEncoder


class TestUUIDEncoder:
    """Tests for the custom JSON encoder."""

    def test_encodes_uuid_as_string(self):
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = json.dumps({"id": test_uuid}, cls=_UUIDEncoder)
        parsed = json.loads(result)
        assert parsed["id"] == "12345678-1234-5678-1234-567812345678"

    def test_encodes_datetime_as_isoformat(self):
        test_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = json.dumps({"timestamp": test_dt}, cls=_UUIDEncoder)
        parsed = json.loads(result)
        assert "2024-01-15" in parsed["timestamp"]

    def test_raises_for_unsupported_types(self):
        with pytest.raises(TypeError):
            json.dumps({"value": set()}, cls=_UUIDEncoder)


class TestEventPublisher:
    """Tests for the EventPublisher class."""

    def setup_method(self):
        self.publisher = EventPublisher()

    @pytest.mark.asyncio
    async def test_publish_skips_when_sns_disabled(self):
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = False
            publisher = EventPublisher()

            await publisher.publish("document_created", {"id": "doc-1"})
            # Should not raise and should not try to create client

    @pytest.mark.asyncio
    async def test_publish_sends_message_when_sns_enabled(self):
        mock_sns_client = MagicMock()
        mock_sns_client.publish = MagicMock(return_value={"MessageId": "msg-123"})

        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123456789:test-topic"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            publisher = EventPublisher()
            publisher._client = mock_sns_client

            await publisher.publish("document_created", {"id": "doc-1", "title": "Test"})

            mock_sns_client.publish.assert_called_once()
            call_kwargs = mock_sns_client.publish.call_args[1]
            assert call_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789:test-topic"

            message = json.loads(call_kwargs["Message"])
            assert message["event_type"] == "document_created"
            assert message["payload"] == {"id": "doc-1", "title": "Test"}
            assert "timestamp" in message

            attrs = call_kwargs["MessageAttributes"]
            assert attrs["event_type"]["StringValue"] == "document_created"

    @pytest.mark.asyncio
    async def test_publish_handles_uuid_in_payload(self):
        mock_sns_client = MagicMock()
        mock_sns_client.publish = MagicMock(return_value={"MessageId": "msg-456"})

        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123456789:test-topic"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            publisher = EventPublisher()
            publisher._client = mock_sns_client

            doc_id = uuid4()
            await publisher.publish("document_updated", {"id": doc_id})

            call_kwargs = mock_sns_client.publish.call_args[1]
            message = json.loads(call_kwargs["Message"])
            assert message["payload"]["id"] == str(doc_id)

    @pytest.mark.asyncio
    async def test_publish_handles_exception_gracefully(self):
        mock_sns_client = MagicMock()
        mock_sns_client.publish = MagicMock(side_effect=Exception("SNS unavailable"))

        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.sns_enabled = True
            mock_settings.sns_topic_arn = "arn:aws:sns:us-east-1:123456789:test-topic"
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            publisher = EventPublisher()
            publisher._client = mock_sns_client

            # Should not raise
            await publisher.publish("document_deleted", {"id": "doc-1"})

    def test_get_client_creates_boto3_client(self):
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.aws_region = "us-west-2"
            mock_settings.aws_endpoint_url = "http://localhost:4566"

            with patch("boto3.client") as mock_boto3:
                mock_boto3.return_value = MagicMock()
                publisher = EventPublisher()
                publisher._get_client()

                mock_boto3.assert_called_once_with(
                    "sns",
                    region_name="us-west-2",
                    endpoint_url="http://localhost:4566",
                )

    def test_get_client_caches_instance(self):
        with patch("app.services.event_publisher.settings") as mock_settings:
            mock_settings.aws_region = "us-east-1"
            mock_settings.aws_endpoint_url = ""

            with patch("boto3.client") as mock_boto3:
                mock_boto3.return_value = MagicMock()
                publisher = EventPublisher()
                client1 = publisher._get_client()
                client2 = publisher._get_client()

                assert client1 is client2
                assert mock_boto3.call_count == 1
