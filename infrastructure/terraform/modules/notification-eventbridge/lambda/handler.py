"""AWS Lambda notification consumer.

Serverless equivalent of the in-cluster Kotlin SqsConsumer + NotificationService.
Triggered by the SQS queue that the EventBridge rule targets. For each record it
parses the domain event, resolves the recipient/preferences/template exactly like
the in-cluster consumer, and persists the notification to the SAME DynamoDB table
so the two paths are behavior-identical.

Uses partial-batch responses (ReportBatchItemFailures): a record that fails to
process is returned to SQS and retried, then dead-lettered after maxReceiveCount,
mirroring the in-cluster consumer's "don't delete on failure" behavior.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import boto3

import notification_core as core

_NOTIFICATIONS_TABLE = os.environ.get("DYNAMODB_TABLE_NOTIFICATIONS", "otterworks-notifications")
_PREFERENCES_TABLE = os.environ.get("DYNAMODB_TABLE_PREFERENCES", "otterworks-notification-preferences")
_SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "notifications@otterworks.io")
_EMAIL_ENABLED = os.environ.get("EMAIL_DELIVERY_ENABLED", "true").lower() == "true"

_AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or None
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_dynamodb = boto3.client("dynamodb", region_name=_AWS_REGION, endpoint_url=_AWS_ENDPOINT_URL)
_ses = boto3.client("ses", region_name=_AWS_REGION, endpoint_url=_AWS_ENDPOINT_URL)


def _get_preferences(user_id: str) -> dict[str, list[str]] | None:
    """Read stored channel preferences; None => fall back to defaults (parity)."""
    try:
        resp = _dynamodb.get_item(
            TableName=_PREFERENCES_TABLE,
            Key={"userId": {"S": user_id}},
        )
    except Exception:  # noqa: BLE001 - matches Kotlin repo fallback-to-defaults
        return None

    item = resp.get("Item")
    if not item or "channels" not in item:
        return None

    channels: dict[str, list[str]] = {}
    for event_type, value in item["channels"].get("M", {}).items():
        chans = []
        for entry in value.get("L", []):
            name = entry.get("S")
            if name in (core.EMAIL, core.IN_APP, core.PUSH):
                chans.append(name)
        channels[event_type] = chans
    return channels


def _send_email(to_address: str, subject: str, html_body: str) -> bool:
    """Parity with EmailSender.sendEmail: success -> True, exception -> False."""
    if not _EMAIL_ENABLED:
        return False
    try:
        _ses.send_email(
            Source=_SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_address]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
            },
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _save_notification(record: core.ProcessedNotification, notification_id: str, created_at: str, delivered_via: list[str]) -> None:
    _dynamodb.put_item(
        TableName=_NOTIFICATIONS_TABLE,
        Item={
            "id": {"S": notification_id},
            "userId": {"S": record.user_id},
            "type": {"S": record.type},
            "title": {"S": record.title},
            "message": {"S": record.message},
            "resourceId": {"S": record.resource_id},
            "resourceType": {"S": record.resource_type},
            "actorId": {"S": record.actor_id},
            "read": {"BOOL": False},
            "deliveredVia": {"L": [{"S": c} for c in delivered_via]},
            "createdAt": {"S": created_at},
        },
    )


def process_event(event: core.NotificationMessage) -> bool:
    """Process one domain event. Returns True if a notification was produced.

    Faithful port of NotificationService.processEvent.
    """
    target_user_id = core.resolve_target_user_id(event)
    if not target_user_id.strip():
        return False

    stored = _get_preferences(target_user_id)
    enabled_channels = core.resolve_channels(event, stored)

    rendered = core.render(event)
    delivered_via: list[str] = []

    if core.IN_APP in enabled_channels:
        delivered_via.append("in_app")

    if core.EMAIL in enabled_channels:
        if _send_email(f"{target_user_id}@otterworks.io", rendered.email_subject, rendered.email_body):
            delivered_via.append("email")

    processed = core.ProcessedNotification(
        user_id=target_user_id,
        type=event.eventType,
        title=rendered.title,
        message=rendered.message,
        resource_id=core.resolve_resource_id(event),
        resource_type=core.resolve_resource_type(event),
        actor_id=event.actorId or event.ownerId,
        channels=enabled_channels,
    )

    notification_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # PUSH is delivered by the in-cluster consumer only when a live WebSocket
    # session exists in that pod's memory; a Lambda holds no such sessions, so
    # the persisted record carries in_app/email identically and never a spurious
    # "push". (See PR notes.)
    _save_notification(processed, notification_id, created_at, delivered_via)
    return True


def handler(event, _context=None):
    """SQS-triggered entrypoint with partial-batch failure reporting."""
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        try:
            parsed = core.parse_message(record.get("body", ""))
            if parsed is not None:
                process_event(parsed)
            # Unparseable messages are dropped (not retried), matching the
            # in-cluster consumer which deletes/acks them as parse failures.
        except Exception:  # noqa: BLE001 - a genuine processing error is retried
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
