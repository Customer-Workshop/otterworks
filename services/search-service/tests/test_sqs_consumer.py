"""Tests for SQS consumer event processing and normalization."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.sqs_consumer import SQSConsumer


@pytest.fixture()
def mock_indexer() -> MagicMock:
    indexer = MagicMock()
    indexer.process_event.return_value = {"status": "ok"}
    return indexer


@pytest.fixture()
def consumer(mock_indexer: MagicMock) -> SQSConsumer:
    return SQSConsumer(
        indexer=mock_indexer,
        queue_url="http://localhost:4566/queue/test",
        region="us-east-1",
        endpoint_url="http://localhost:4566",
    )


class TestNormalizeEvent:
    """Tests for _normalize_event static method."""

    def test_snake_case_document_created(self):
        body = {
            "event_type": "document_created",
            "payload": {"id": "doc-1", "title": "Test"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_document"
        assert result["data"]["id"] == "doc-1"

    def test_snake_case_document_deleted(self):
        body = {
            "event_type": "document_deleted",
            "payload": {"id": "doc-1"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_snake_case_file_uploaded(self):
        body = {
            "event_type": "file_uploaded",
            "payload": {"id": "file-1", "name": "test.txt"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"

    def test_snake_case_file_trashed(self):
        body = {
            "event_type": "file_trashed",
            "payload": {"id": "file-1"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_snake_case_unknown_event_passes_through(self):
        body = {
            "event_type": "custom_event",
            "payload": {"id": "x"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "custom_event"

    def test_camel_case_file_uploaded(self):
        body = {
            "eventType": "file_uploaded",
            "fileId": "file-1",
            "name": "test.txt",
            "mimeType": "text/plain",
            "ownerId": "user-1",
            "folderId": "folder-1",
            "sizeBytes": 1024,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"
        assert result["data"]["id"] == "file-1"
        assert result["data"]["name"] == "test.txt"
        assert result["data"]["mime_type"] == "text/plain"
        assert result["data"]["owner_id"] == "user-1"

    def test_camel_case_file_deleted(self):
        body = {
            "eventType": "file_deleted",
            "fileId": "file-1",
            "ownerId": "user-1",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"
        assert result["data"]["type"] == "file"
        assert result["data"]["id"] == "file-1"

    def test_camel_case_file_trashed(self):
        body = {
            "eventType": "file_trashed",
            "fileId": "file-2",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_camel_case_unknown_event_passes_through(self):
        body = {
            "eventType": "file_shared",
            "fileId": "file-1",
        }
        result = SQSConsumer._normalize_event(body)
        assert result == body

    def test_already_normalized_passthrough(self):
        body = {
            "action": "index_document",
            "data": {"id": "doc-1", "title": "Test"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result == body


class TestProcessMessage:
    """Tests for _process_message."""

    def test_processes_valid_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        sqs = MagicMock()
        message = {
            "ReceiptHandle": "receipt-1",
            "MessageId": "msg-1",
            "Body": json.dumps({
                "action": "index_document",
                "data": {"id": "doc-1", "title": "Test"},
            }),
        }

        consumer._process_message(sqs, message)
        mock_indexer.process_event.assert_called_once()
        sqs.delete_message.assert_called_once()

    def test_handles_sns_wrapped_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        sqs = MagicMock()
        inner = {"action": "index_document", "data": {"id": "doc-1"}}
        message = {
            "ReceiptHandle": "receipt-2",
            "MessageId": "msg-2",
            "Body": json.dumps({
                "Message": json.dumps(inner),
                "TopicArn": "arn:aws:sns:us-east-1:123:topic",
            }),
        }

        consumer._process_message(sqs, message)
        mock_indexer.process_event.assert_called_once()
        sqs.delete_message.assert_called_once()

    def test_deletes_invalid_json_message(self, consumer: SQSConsumer):
        sqs = MagicMock()
        message = {
            "ReceiptHandle": "receipt-3",
            "MessageId": "msg-3",
            "Body": "not valid json{",
        }

        consumer._process_message(sqs, message)
        sqs.delete_message.assert_called_once()

    def test_deletes_message_on_value_error(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_indexer.process_event.side_effect = ValueError("bad data")
        sqs = MagicMock()
        message = {
            "ReceiptHandle": "receipt-4",
            "MessageId": "msg-4",
            "Body": json.dumps({"action": "index_document", "data": {}}),
        }

        consumer._process_message(sqs, message)
        sqs.delete_message.assert_called_once()

    def test_does_not_delete_on_unexpected_error(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_indexer.process_event.side_effect = RuntimeError("unexpected")
        sqs = MagicMock()
        message = {
            "ReceiptHandle": "receipt-5",
            "MessageId": "msg-5",
            "Body": json.dumps({"action": "index_document", "data": {}}),
        }

        consumer._process_message(sqs, message)
        sqs.delete_message.assert_not_called()


class TestStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_skips_without_queue_url(self):
        consumer = SQSConsumer(
            indexer=MagicMock(),
            queue_url="",
        )
        consumer.start()
        assert consumer._thread is None

    def test_stop_when_not_started(self, consumer: SQSConsumer):
        consumer.stop()
        assert not consumer._running
