import json

from bridge import bridge


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.content = json.dumps(body or {}).encode()

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response


class FakeSqs:
    def __init__(self):
        self.deleted = []

    def receive_message(self, **_kwargs):
        return {"Messages": []}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def test_document_mapping_is_deterministic():
    event = {
        "event_type": "document_created",
        "timestamp": "2026-09-19T00:00:00Z",
        "payload": {"id": "doc-1", "owner_id": "tenant-1"},
    }
    mapped = bridge.map_event(event)
    assert mapped == {
        "event_id": bridge.deterministic_event_id(
            "document_created", "doc-1", "2026-09-19T00:00:00Z"
        ),
        "tenant_id": "tenant-1",
        "email": None,
        "kind": "api",
        "units": 1,
        "occurred_at": "2026-09-19T00:00:00Z",
    }
    assert mapped["event_id"] == bridge.map_event(event)["event_id"]


def test_file_upload_uses_megabyte_units():
    mapped = bridge.map_event({
        "eventType": "file_uploaded",
        "fileId": "file-1",
        "ownerId": "tenant-1",
        "sizeBytes": 1_048_577,
        "timestamp": "2026-09-19T00:00:00Z",
    })
    assert mapped["kind"] == "storage"
    assert mapped["units"] == 2


def test_unsupported_event_is_skipped():
    assert bridge.map_event({"event_type": "file_deleted"}) is None


def test_duplicate_response_is_deleted_and_counted():
    sqs = FakeSqs()
    session = FakeSession(FakeResponse(200, {"status": "duplicate"}))
    usage = bridge.UsageBridge(sqs_client=sqs, sns_client=object(), http_session=session)
    message = {"Body": json.dumps({
        "event_type": "document_created",
        "timestamp": "2026-09-19T00:00:00Z",
        "payload": {"id": "doc-1", "owner_id": "tenant-1"},
    }), "ReceiptHandle": "receipt-1"}
    assert usage.process_message(message)
    assert usage.metrics.snapshot()["duplicate"] == 1
