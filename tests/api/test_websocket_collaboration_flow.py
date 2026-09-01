import os
import time

import pytest
import socketio


pytestmark = [pytest.mark.api_flow, pytest.mark.websocket]


def _collab_url(base_url: str) -> str:
    return os.getenv("OTTERWORKS_COLLAB_WS_URL", base_url.replace("http://", "ws://").replace("https://", "wss://"))


def test_socketio_rejects_missing_or_invalid_token(base_url):
    sio = socketio.Client(reconnection=False, request_timeout=3)
    with pytest.raises(socketio.exceptions.ConnectionError):
        sio.connect(_collab_url(base_url), transports=["websocket"])

    invalid = socketio.Client(reconnection=False, request_timeout=3)
    with pytest.raises(socketio.exceptions.ConnectionError):
        invalid.connect(
            _collab_url(base_url),
            auth={"token": "not-a-valid-token"},
            transports=["websocket"],
        )


def test_socketio_two_users_join_same_document_and_presence_updates(api_client, base_url):
    user_a = api_client.register_user("ws-user-a")
    document = api_client.create_document(
        user_a,
        title=f"WebSocket Document {api_client.run_id}",
        content="collaboration body",
    )
    document_id = document["id"]
    received_by_second_owner: list[dict] = []

    client_a = socketio.Client(reconnection=False, request_timeout=5)
    second_owner = socketio.Client(reconnection=False, request_timeout=5)

    @second_owner.on("document-update")
    def on_document_update(data):
        received_by_second_owner.append(data)

    try:
        client_a.connect(_collab_url(base_url), auth={"token": user_a.access_token}, transports=["websocket"])
        second_owner.connect(_collab_url(base_url), auth={"token": user_a.access_token}, transports=["websocket"])

        client_a.emit("join-document", {"documentId": document_id})
        second_owner.emit("join-document", {"documentId": document_id})
        time.sleep(0.5)

        presence_response = api_client.client.get(
            f"/api/v1/collab/documents/{document_id}/presence",
            headers=user_a.auth_headers,
        )
        assert presence_response.status_code == 200, presence_response.text

        client_a.emit(
            "document-update",
            {"documentId": document_id, "update": {"text": f"hello {api_client.run_id}"}},
        )

        api_client.poll_until(
            lambda: received_by_second_owner,
            lambda updates: len(updates) >= 1,
            timeout_seconds=10,
            interval_seconds=0.25,
            description="collaboration update fanout to second socket client",
        )
    finally:
        if client_a.connected:
            client_a.disconnect()
        if second_owner.connected:
            second_owner.disconnect()


def test_socketio_non_owner_cannot_join_document(api_client, base_url):
    user_a = api_client.register_user("ws-owner")
    user_b = api_client.register_user("ws-non-owner")
    document = api_client.create_document(
        user_a,
        title=f"Unauthorized WebSocket Document {api_client.run_id}",
        content="private collaboration body",
    )
    document_id = document["id"]
    denied_events: list[dict] = []
    sync_events: list[dict] = []
    client = socketio.Client(reconnection=False, request_timeout=5)

    @client.on("document-access-denied")
    def on_document_access_denied(data):
        denied_events.append(data)

    @client.on("sync-document")
    def on_sync_document(data):
        sync_events.append(data)

    try:
        client.connect(_collab_url(base_url), auth={"token": user_b.access_token}, transports=["websocket"])
        response = client.call("join-document", {"documentId": document_id}, timeout=5)

        assert response["success"] is False
        assert response["error"] == "Not authorized for this document"
        api_client.poll_until(
            lambda: denied_events,
            lambda events: len(events) >= 1,
            timeout_seconds=5,
            interval_seconds=0.25,
            description="document access denied event",
        )
        assert denied_events[0] == {
            "documentId": document_id,
            "error": "Not authorized for this document",
        }
        assert not sync_events
    finally:
        if client.connected:
            client.disconnect()
