"""Parity tests for the serverless notification consumer core logic.

These assert the Python port produces the same recipient/resource/template/
channel decisions as the in-cluster Kotlin consumer, so the re-architected
EventBridge -> SQS -> Lambda path is behavior-identical.

Run: python -m pytest test_handler.py   (pure logic, no AWS required)
"""

import json

import notification_core as core


def _eb_envelope(detail: dict, detail_type: str, source: str = "otterworks.file-service") -> str:
    """An EventBridge-to-SQS delivery envelope."""
    return json.dumps(
        {
            "version": "0",
            "id": "abc-123",
            "detail-type": detail_type,
            "source": source,
            "account": "000000000000",
            "time": "2024-01-01T00:00:00Z",
            "region": "us-east-1",
            "resources": [],
            "detail": detail,
        }
    )


FILE_SHARED = {
    "eventType": "file_shared",
    "fileId": "file-1",
    "ownerId": "owner-1",
    "sharedWithUserId": "recipient-1",
    "timestamp": "2024-01-01T00:00:00Z",
}


def test_parse_direct_message():
    msg = core.parse_message(json.dumps(FILE_SHARED))
    assert msg is not None
    assert msg.eventType == "file_shared"
    assert msg.sharedWithUserId == "recipient-1"


def test_parse_eventbridge_envelope():
    msg = core.parse_message(_eb_envelope(FILE_SHARED, "file_shared"))
    assert msg is not None
    assert msg.eventType == "file_shared"
    assert msg.fileId == "file-1"
    assert msg.sharedWithUserId == "recipient-1"


def test_parse_eventbridge_envelope_string_detail():
    body = json.dumps({"detail-type": "file_shared", "source": "x", "detail": json.dumps(FILE_SHARED)})
    msg = core.parse_message(body)
    assert msg is not None
    assert msg.sharedWithUserId == "recipient-1"


def test_parse_sns_envelope():
    body = json.dumps({"Type": "Notification", "MessageId": "m1", "Message": json.dumps(FILE_SHARED)})
    msg = core.parse_message(body)
    assert msg is not None
    assert msg.eventType == "file_shared"


def test_parse_garbage_returns_none():
    assert core.parse_message("not json") is None
    assert core.parse_message(json.dumps({"foo": "bar"})) is None


def test_resolve_target_user_id_per_event():
    fs = core.NotificationMessage(eventType="file_shared", timestamp="t", sharedWithUserId="u-share")
    assert core.resolve_target_user_id(fs) == "u-share"

    ca = core.NotificationMessage(eventType="comment_added", timestamp="t", ownerId="u-owner")
    assert core.resolve_target_user_id(ca) == "u-owner"

    ca2 = core.NotificationMessage(eventType="comment_added", timestamp="t", userId="u-user", ownerId="u-owner")
    assert core.resolve_target_user_id(ca2) == "u-user"

    um = core.NotificationMessage(eventType="user_mentioned", timestamp="t", userId="u-user")
    assert core.resolve_target_user_id(um) == "u-user"

    um2 = core.NotificationMessage(eventType="user_mentioned", timestamp="t", mentionedUserId="u-m", userId="u-user")
    assert core.resolve_target_user_id(um2) == "u-m"


def test_resolve_resource_id_and_type():
    fs = core.NotificationMessage(eventType="file_shared", timestamp="t", fileId="f1")
    assert core.resolve_resource_id(fs) == "f1"
    assert core.resolve_resource_type(fs) == "file"

    ca = core.NotificationMessage(eventType="comment_added", timestamp="t", documentId="d1")
    assert core.resolve_resource_id(ca) == "d1"
    assert core.resolve_resource_type(ca) == "comment"

    ca2 = core.NotificationMessage(eventType="comment_added", timestamp="t", commentId="c1", documentId="d1")
    assert core.resolve_resource_id(ca2) == "c1"


def test_render_file_shared_matches_template():
    msg = core.NotificationMessage(
        eventType="file_shared", timestamp="t", fileId="file-1", actorId="actor-9"
    )
    rendered = core.render(msg)
    assert rendered.title == "File Shared With You"
    assert rendered.message == "A file has been shared with you by user actor-9."
    assert rendered.email_subject == "OtterWorks: A file has been shared with you"
    assert "A file (ID: file-1) has been shared with you by user actor-9." in rendered.email_body


def test_render_actor_falls_back_to_owner():
    msg = core.NotificationMessage(eventType="comment_added", timestamp="t", documentId="d1", ownerId="owner-x")
    rendered = core.render(msg)
    assert "by user owner-x" in rendered.message


def test_default_channels():
    assert core.resolve_channels(core.NotificationMessage("file_shared", "t"), None) == [
        core.EMAIL,
        core.IN_APP,
        core.PUSH,
    ]
    assert core.resolve_channels(core.NotificationMessage("document_edited", "t"), None) == [core.IN_APP]


def test_stored_channels_override_defaults():
    stored = {"file_shared": [core.IN_APP]}
    assert core.resolve_channels(core.NotificationMessage("file_shared", "t"), stored) == [core.IN_APP]


def test_unknown_event_defaults_in_app():
    assert core.resolve_channels(core.NotificationMessage("weird_event", "t"), None) == [core.IN_APP]
