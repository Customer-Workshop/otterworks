"""Pure, side-effect-free notification processing logic.

This is a faithful Python port of the Kotlin in-cluster consumer so the
serverless (Lambda) path is behavior-identical to it:

  * message parsing  -> SqsConsumer.parseMessage
  * user/resource resolution -> NotificationService.resolveTargetUserId / *ResourceId / *ResourceType
  * templating -> NotificationTemplates.render
  * default preferences -> NotificationPreference defaults

Keeping this module free of boto3 makes it unit-testable without AWS and lets
the parity tests assert identical output for identical domain events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Delivery channels (parity with model.DeliveryChannel).
EMAIL = "EMAIL"
IN_APP = "IN_APP"
PUSH = "PUSH"

# Default per-event channel preferences (parity with model.NotificationPreference).
DEFAULT_PREFERENCES: dict[str, list[str]] = {
    "file_shared": [EMAIL, IN_APP, PUSH],
    "comment_added": [IN_APP, PUSH],
    "document_edited": [IN_APP],
    "user_mentioned": [EMAIL, IN_APP, PUSH],
}

# Fields of SqsNotificationMessage (parity with model.SqsNotificationMessage).
_MESSAGE_STRING_FIELDS = (
    "eventType",
    "fileId",
    "ownerId",
    "sharedWithUserId",
    "documentId",
    "commentId",
    "userId",
    "actorId",
    "mentionedUserId",
    "timestamp",
)


@dataclass
class NotificationMessage:
    """Parity with model.SqsNotificationMessage."""

    eventType: str
    timestamp: str
    fileId: str = ""
    ownerId: str = ""
    sharedWithUserId: str = ""
    documentId: str = ""
    commentId: str = ""
    userId: str = ""
    actorId: str = ""
    mentionedUserId: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationMessage":
        # eventType and timestamp are required (matches Kotlin's non-null fields);
        # a KeyError here means the payload is not a notification message.
        return cls(
            eventType=data["eventType"],
            timestamp=data["timestamp"],
            fileId=str(data.get("fileId", "") or ""),
            ownerId=str(data.get("ownerId", "") or ""),
            sharedWithUserId=str(data.get("sharedWithUserId", "") or ""),
            documentId=str(data.get("documentId", "") or ""),
            commentId=str(data.get("commentId", "") or ""),
            userId=str(data.get("userId", "") or ""),
            actorId=str(data.get("actorId", "") or ""),
            mentionedUserId=str(data.get("mentionedUserId", "") or ""),
        )


@dataclass
class RenderedNotification:
    title: str
    message: str
    email_subject: str
    email_body: str


@dataclass
class ProcessedNotification:
    """The durable notification record + the delivery channels resolved for it."""

    user_id: str
    type: str
    title: str
    message: str
    resource_id: str
    resource_type: str
    actor_id: str
    channels: list[str] = field(default_factory=list)


# --- Message parsing (parity with SqsConsumer.parseMessage) -------------------


def parse_message(body: str) -> NotificationMessage | None:
    """Parse an SQS body into a NotificationMessage.

    Handles, in order (lenient, ignoring unknown keys — parity with the Kotlin
    consumer's tolerant Json parser):
      1. a direct SqsNotificationMessage JSON object
      2. an EventBridge envelope ({"detail-type", "source", "detail": {...}})
         — the shape delivered when an EventBridge rule targets SQS
      3. an SNS envelope ({"Message": "<json string>"}) — kept so the Lambda
         can also drain the legacy SNS->SQS queue if pointed at it
    Returns None when the body is not a parseable notification message.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    # 1. direct message
    if "eventType" in data and "timestamp" in data:
        try:
            return NotificationMessage.from_dict(data)
        except KeyError:
            pass

    # 2. EventBridge envelope: the domain event lives under "detail"
    detail = data.get("detail")
    if isinstance(detail, dict):
        try:
            return NotificationMessage.from_dict(detail)
        except KeyError:
            return None
    if isinstance(detail, str):
        try:
            return NotificationMessage.from_dict(json.loads(detail))
        except (KeyError, json.JSONDecodeError, TypeError):
            return None

    # 3. SNS envelope
    inner = data.get("Message")
    if isinstance(inner, str):
        try:
            return NotificationMessage.from_dict(json.loads(inner))
        except (KeyError, json.JSONDecodeError, TypeError):
            return None

    return None


# --- Resolution (parity with NotificationService companion object) ------------


def resolve_target_user_id(event: NotificationMessage) -> str:
    if event.eventType == "file_shared":
        return event.sharedWithUserId
    if event.eventType == "comment_added":
        return event.userId or event.ownerId
    if event.eventType == "document_edited":
        return event.userId or event.ownerId
    if event.eventType == "user_mentioned":
        return event.mentionedUserId or event.userId
    return event.userId


def resolve_resource_id(event: NotificationMessage) -> str:
    if event.eventType == "file_shared":
        return event.fileId
    if event.eventType == "comment_added":
        return event.commentId or event.documentId
    if event.eventType == "document_edited":
        return event.documentId
    if event.eventType == "user_mentioned":
        return event.documentId
    return ""


def resolve_resource_type(event: NotificationMessage) -> str:
    return {
        "file_shared": "file",
        "comment_added": "comment",
        "document_edited": "document",
        "user_mentioned": "document",
    }.get(event.eventType, "unknown")


# --- Templating (parity with NotificationTemplates) ---------------------------

_TEMPLATES: dict[str, dict[str, str]] = {
    "file_shared": {
        "title": "File Shared With You",
        "message": "A file has been shared with you by user {{actorId}}.",
        "email_subject": "OtterWorks: A file has been shared with you",
        "email_body": (
            "<html>\n<body>\n    <h2>File Shared</h2>\n"
            "    <p>A file (ID: {{fileId}}) has been shared with you by user {{actorId}}.</p>\n"
            "    <p>Log in to OtterWorks to view the file.</p>\n    <br/>\n"
            '    <p style="color: #888;">\u2014 OtterWorks Notification Service</p>\n'
            "</body>\n</html>"
        ),
    },
    "comment_added": {
        "title": "New Comment",
        "message": "A new comment was added by user {{actorId}} on document {{documentId}}.",
        "email_subject": "OtterWorks: New comment on your document",
        "email_body": (
            "<html>\n<body>\n    <h2>New Comment</h2>\n"
            "    <p>User {{actorId}} added a comment on document {{documentId}}.</p>\n"
            "    <p>Log in to OtterWorks to view the comment.</p>\n    <br/>\n"
            '    <p style="color: #888;">\u2014 OtterWorks Notification Service</p>\n'
            "</body>\n</html>"
        ),
    },
    "document_edited": {
        "title": "Document Edited",
        "message": "Document {{documentId}} was edited by user {{actorId}}.",
        "email_subject": "OtterWorks: A document you follow was edited",
        "email_body": (
            "<html>\n<body>\n    <h2>Document Edited</h2>\n"
            "    <p>Document {{documentId}} was edited by user {{actorId}}.</p>\n"
            "    <p>Log in to OtterWorks to view the changes.</p>\n    <br/>\n"
            '    <p style="color: #888;">\u2014 OtterWorks Notification Service</p>\n'
            "</body>\n</html>"
        ),
    },
    "user_mentioned": {
        "title": "You Were Mentioned",
        "message": "You were mentioned by user {{actorId}} in document {{documentId}}.",
        "email_subject": "OtterWorks: You were mentioned in a document",
        "email_body": (
            "<html>\n<body>\n    <h2>You Were Mentioned</h2>\n"
            "    <p>User {{actorId}} mentioned you in document {{documentId}}.</p>\n"
            "    <p>Log in to OtterWorks to see the context.</p>\n    <br/>\n"
            '    <p style="color: #888;">\u2014 OtterWorks Notification Service</p>\n'
            "</body>\n</html>"
        ),
    },
}


def _replace_variables(template: str, variables: dict[str, str]) -> str:
    result = template
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def render(event: NotificationMessage) -> RenderedNotification:
    template = _TEMPLATES.get(event.eventType)
    if template is None:
        return RenderedNotification(
            title="Notification",
            message="You have a new notification.",
            email_subject="OtterWorks: New notification",
            email_body="<html><body><p>You have a new notification.</p></body></html>",
        )

    variables = {
        "actorId": event.actorId or event.ownerId,
        "fileId": event.fileId,
        "documentId": event.documentId,
        "commentId": event.commentId,
        "userId": event.userId,
    }
    return RenderedNotification(
        title=_replace_variables(template["title"], variables),
        message=_replace_variables(template["message"], variables),
        email_subject=_replace_variables(template["email_subject"], variables),
        email_body=_replace_variables(template["email_body"], variables),
    )


# --- Channel resolution (parity with NotificationService.processEvent) --------


def resolve_channels(event: NotificationMessage, stored_preferences: dict[str, list[str]] | None) -> list[str]:
    """Resolve enabled delivery channels for an event.

    Mirrors NotificationService.processEvent:
      preferences.channels[eventType]
        ?: default NotificationPreference.channels[eventType]
        ?: [IN_APP]
    """
    if stored_preferences and event.eventType in stored_preferences:
        return stored_preferences[event.eventType]
    if event.eventType in DEFAULT_PREFERENCES:
        return DEFAULT_PREFERENCES[event.eventType]
    return [IN_APP]
