"""Tests for SQS consumer event normalization and message processing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.sqs_consumer import SQSConsumer


@pytest.fixture()
def mock_indexer() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def consumer(mock_indexer: MagicMock) -> SQSConsumer:
    return SQSConsumer(
        indexer=mock_indexer,
        queue_url="http://localhost:4566/queue/test",
        region="us-east-1",
        endpoint_url="http://localhost:4566",
    )


class TestNormalizeEvent:
    """Tests for SQSConsumer._normalize_event — the critical data transformation."""

    def test_document_created_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "document_created",
            "payload": {"id": "doc-1", "title": "Test"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_document"
        assert result["data"]["id"] == "doc-1"

    def test_document_updated_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "document_updated",
            "payload": {"id": "doc-2"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_document"

    def test_document_deleted_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "document_deleted",
            "payload": {"id": "doc-3"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_file_uploaded_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "file_uploaded",
            "payload": {"id": "file-1", "name": "report.pdf"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"

    def test_file_deleted_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "file_deleted",
            "payload": {"id": "file-2"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_file_trashed_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "file_trashed",
            "payload": {"id": "file-3"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_file_restored_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "file_restored",
            "payload": {"id": "file-4"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"

    def test_unknown_event_type_snake_case(self, consumer: SQSConsumer):
        body = {
            "event_type": "custom_event",
            "payload": {"id": "x"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "custom_event"

    # --- camelCase format (file-service) ---

    def test_file_uploaded_camel_case(self, consumer: SQSConsumer):
        body = {
            "eventType": "file_uploaded",
            "fileId": "f-1",
            "ownerId": "owner-1",
            "name": "photo.jpg",
            "mimeType": "image/jpeg",
            "sizeBytes": 1024,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"
        assert result["data"]["id"] == "f-1"
        assert result["data"]["name"] == "photo.jpg"
        assert result["data"]["mime_type"] == "image/jpeg"
        assert result["data"]["owner_id"] == "owner-1"
        assert result["data"]["size"] == 1024

    def test_file_deleted_camel_case(self, consumer: SQSConsumer):
        body = {
            "eventType": "file_deleted",
            "fileId": "f-2",
            "ownerId": "owner-1",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"
        assert result["data"]["type"] == "file"
        assert result["data"]["id"] == "f-2"

    def test_file_trashed_camel_case(self, consumer: SQSConsumer):
        body = {
            "eventType": "file_trashed",
            "fileId": "f-3",
            "ownerId": "owner-1",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_file_shared_camel_case_skipped(self, consumer: SQSConsumer):
        """file_shared events can't be indexed — should pass through unchanged."""
        body = {
            "eventType": "file_shared",
            "fileId": "f-4",
            "ownerId": "owner-1",
        }
        result = SQSConsumer._normalize_event(body)
        assert result == body  # passed through unchanged

    def test_file_moved_camel_case_skipped(self, consumer: SQSConsumer):
        """file_moved events can't be indexed — should pass through unchanged."""
        body = {
            "eventType": "file_moved",
            "fileId": "f-5",
        }
        result = SQSConsumer._normalize_event(body)
        assert result == body

    # --- already in indexer format ---

    def test_passthrough_for_indexer_format(self, consumer: SQSConsumer):
        body = {"action": "index_document", "data": {"id": "d-1"}}
        result = SQSConsumer._normalize_event(body)
        assert result == body


class TestProcessMessage:
    def test_processes_valid_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        mock_indexer.process_event.return_value = "ok"

        message = {
            "Body": json.dumps({
                "event_type": "document_created",
                "payload": {"id": "doc-1"},
            }),
            "ReceiptHandle": "receipt-1",
            "MessageId": "msg-1",
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_called_once()
        mock_sqs.delete_message.assert_called_once()

    def test_processes_sns_wrapped_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        mock_indexer.process_event.return_value = "ok"

        inner = json.dumps({"event_type": "document_updated", "payload": {"id": "doc-2"}})
        message = {
            "Body": json.dumps({
                "Message": inner,
                "TopicArn": "arn:aws:sns:us-east-1:123:topic",
            }),
            "ReceiptHandle": "receipt-2",
            "MessageId": "msg-2",
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_called_once()
        mock_sqs.delete_message.assert_called_once()

    def test_handles_invalid_json(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()

        message = {
            "Body": "not-valid-json",
            "ReceiptHandle": "receipt-3",
            "MessageId": "msg-3",
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_not_called()
        mock_sqs.delete_message.assert_called_once()


class TestStartStop:
    def test_start_skips_when_no_queue_url(self, mock_indexer: MagicMock):
        consumer = SQSConsumer(indexer=mock_indexer, queue_url="")
        consumer.start()
        assert consumer._thread is None

    def test_stop_when_not_started(self, consumer: SQSConsumer):
        consumer.stop()
        assert not consumer._running
