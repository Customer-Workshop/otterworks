"""Tests for the SQS consumer service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.sqs_consumer import SQSConsumer


@pytest.fixture()
def mock_indexer() -> MagicMock:
    """Create a mock Indexer."""
    indexer = MagicMock()
    indexer.process_event.return_value = {"status": "ok"}
    return indexer


@pytest.fixture()
def consumer(mock_indexer: MagicMock) -> SQSConsumer:
    """Create an SQSConsumer with a mock indexer."""
    return SQSConsumer(
        indexer=mock_indexer,
        queue_url="http://localhost:4566/000000000000/test-queue",
        region="us-east-1",
        endpoint_url="http://localhost:4566",
    )


class TestSQSConsumerInit:
    """Tests for SQSConsumer initialization."""

    def test_stores_configuration(self, mock_indexer: MagicMock):
        consumer = SQSConsumer(
            indexer=mock_indexer,
            queue_url="http://queue-url",
            region="eu-west-1",
            endpoint_url="http://localstack:4566",
            max_messages=5,
            wait_time_seconds=10,
            visibility_timeout=30,
        )

        assert consumer.queue_url == "http://queue-url"
        assert consumer.region == "eu-west-1"
        assert consumer.endpoint_url == "http://localstack:4566"
        assert consumer.max_messages == 5
        assert consumer.wait_time_seconds == 10
        assert consumer.visibility_timeout == 30

    def test_defaults(self, mock_indexer: MagicMock):
        consumer = SQSConsumer(indexer=mock_indexer, queue_url="http://queue")

        assert consumer.region == "us-east-1"
        assert consumer.endpoint_url == ""
        assert consumer.max_messages == 10
        assert consumer.wait_time_seconds == 20
        assert consumer.visibility_timeout == 60


class TestSQSConsumerStart:
    """Tests for start/stop lifecycle."""

    def test_start_skips_when_no_queue_url(self, mock_indexer: MagicMock):
        consumer = SQSConsumer(indexer=mock_indexer, queue_url="")
        consumer.start()
        assert consumer._thread is None

    def test_start_creates_daemon_thread(self, consumer: SQSConsumer):
        with patch.object(consumer, "_poll_loop"):
            consumer.start()
            assert consumer._running is True
            assert consumer._thread is not None
            assert consumer._thread.daemon is True
            consumer.stop()

    def test_stop_sets_running_false(self, consumer: SQSConsumer):
        consumer._running = True
        consumer.stop()
        assert consumer._running is False


class TestNormalizeEvent:
    """Tests for the _normalize_event static method."""

    def test_snake_case_document_created(self):
        body = {
            "event_type": "document_created",
            "payload": {"id": "doc-1", "title": "Test Doc"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_document"
        assert result["data"] == {"id": "doc-1", "title": "Test Doc"}

    def test_snake_case_document_deleted(self):
        body = {
            "event_type": "document_deleted",
            "payload": {"id": "doc-2"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"
        assert result["data"] == {"id": "doc-2"}

    def test_snake_case_file_uploaded(self):
        body = {
            "event_type": "file_uploaded",
            "payload": {"id": "file-1", "name": "photo.jpg"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"

    def test_snake_case_file_trashed(self):
        body = {
            "event_type": "file_trashed",
            "payload": {"id": "file-2"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"

    def test_snake_case_file_restored(self):
        body = {
            "event_type": "file_restored",
            "payload": {"id": "file-3", "name": "restored.txt"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"

    def test_snake_case_unknown_event_type(self):
        body = {
            "event_type": "unknown_event",
            "payload": {"id": "x"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "unknown_event"

    def test_camel_case_file_uploaded(self):
        body = {
            "eventType": "file_uploaded",
            "fileId": "file-abc",
            "name": "report.pdf",
            "mimeType": "application/pdf",
            "ownerId": "user-1",
            "folderId": "folder-1",
            "sizeBytes": 1024,
            "tags": ["important"],
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "index_file"
        assert result["data"]["id"] == "file-abc"
        assert result["data"]["name"] == "report.pdf"
        assert result["data"]["mime_type"] == "application/pdf"
        assert result["data"]["owner_id"] == "user-1"
        assert result["data"]["folder_id"] == "folder-1"
        assert result["data"]["size"] == 1024
        assert result["data"]["tags"] == ["important"]

    def test_camel_case_file_deleted(self):
        body = {
            "eventType": "file_deleted",
            "fileId": "file-del",
        }
        result = SQSConsumer._normalize_event(body)
        assert result["action"] == "delete"
        assert result["data"]["type"] == "file"
        assert result["data"]["id"] == "file-del"

    def test_camel_case_file_shared_skipped(self):
        body = {
            "eventType": "file_shared",
            "fileId": "file-shared",
        }
        result = SQSConsumer._normalize_event(body)
        # file_shared is not in action_map so returns body unchanged
        assert result == body

    def test_already_normalized_format(self):
        body = {
            "action": "index_document",
            "data": {"id": "doc-1", "title": "Test"},
        }
        result = SQSConsumer._normalize_event(body)
        assert result == body


class TestProcessMessage:
    """Tests for _process_message."""

    def test_processes_valid_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        message = {
            "MessageId": "msg-1",
            "ReceiptHandle": "receipt-1",
            "Body": json.dumps({"action": "index_document", "data": {"id": "doc-1"}}),
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_called_once_with(
            {"action": "index_document", "data": {"id": "doc-1"}}
        )
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=consumer.queue_url, ReceiptHandle="receipt-1"
        )

    def test_processes_sns_wrapped_message(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        inner_message = {"action": "index_file", "data": {"id": "file-1"}}
        message = {
            "MessageId": "msg-2",
            "ReceiptHandle": "receipt-2",
            "Body": json.dumps({
                "Message": json.dumps(inner_message),
                "TopicArn": "arn:aws:sns:us-east-1:123:topic",
            }),
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_called_once_with(inner_message)
        mock_sqs.delete_message.assert_called_once()

    def test_handles_invalid_json(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        message = {
            "MessageId": "msg-bad",
            "ReceiptHandle": "receipt-bad",
            "Body": "not valid json{{{",
        }

        consumer._process_message(mock_sqs, message)

        mock_indexer.process_event.assert_not_called()
        mock_sqs.delete_message.assert_called_once()

    def test_handles_processing_exception(self, consumer: SQSConsumer, mock_indexer: MagicMock):
        mock_sqs = MagicMock()
        mock_indexer.process_event.side_effect = Exception("Processing failed")

        message = {
            "MessageId": "msg-err",
            "ReceiptHandle": "receipt-err",
            "Body": json.dumps({"action": "index_document", "data": {"id": "doc-x"}}),
        }

        # Should not raise
        consumer._process_message(mock_sqs, message)
        # Message should NOT be deleted on unexpected exception
        mock_sqs.delete_message.assert_not_called()
