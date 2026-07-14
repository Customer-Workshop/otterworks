"""Tests for the EventPublisher SNS/EventBridge backend selection.

Verifies that flipping ``event_backend`` to ``eventbridge`` publishes the
byte-identical event body via EventBridge PutEvents, while the default keeps
the SNS path — so the two consumer paths receive identical events.
"""

import json
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.services.event_publisher import EventPublisher


@pytest.fixture
def restore_settings():
    saved = (
        settings.event_backend,
        settings.sns_enabled,
        settings.sns_topic_arn,
        settings.eventbridge_bus_name,
    )
    yield
    (
        settings.event_backend,
        settings.sns_enabled,
        settings.sns_topic_arn,
        settings.eventbridge_bus_name,
    ) = saved


async def test_default_backend_uses_sns(restore_settings):
    settings.event_backend = "sns"
    settings.sns_enabled = True
    settings.sns_topic_arn = "arn:aws:sns:us-east-1:000000000000:otterworks-events"

    sns = MagicMock()
    pub = EventPublisher()
    pub._client = sns

    await pub.publish("comment_added", {"comment_id": "c1", "document_id": "d1"})

    sns.publish.assert_called_once()
    _, kwargs = sns.publish.call_args
    assert kwargs["TopicArn"] == settings.sns_topic_arn
    body = json.loads(kwargs["Message"])
    assert body["event_type"] == "comment_added"
    assert body["payload"] == {"comment_id": "c1", "document_id": "d1"}


async def test_eventbridge_backend_puts_events(restore_settings):
    settings.event_backend = "eventbridge"
    settings.eventbridge_bus_name = "otterworks-notifications-eb-dev-ebns1"

    eb = MagicMock()
    sns = MagicMock()
    pub = EventPublisher()
    pub._eb_client = eb
    pub._client = sns

    await pub.publish("comment_added", {"comment_id": "c1", "document_id": "d1"})

    # SNS must not be touched when EventBridge is selected.
    sns.publish.assert_not_called()
    eb.put_events.assert_called_once()
    _, kwargs = eb.put_events.call_args
    entry = kwargs["Entries"][0]
    assert entry["EventBusName"] == "otterworks-notifications-eb-dev-ebns1"
    assert entry["Source"] == "otterworks.document-service"
    assert entry["DetailType"] == "comment_added"
    detail = json.loads(entry["Detail"])
    assert detail["event_type"] == "comment_added"
    assert detail["payload"] == {"comment_id": "c1", "document_id": "d1"}


async def test_eventbridge_without_bus_is_noop(restore_settings):
    settings.event_backend = "eventbridge"
    settings.eventbridge_bus_name = ""

    eb = MagicMock()
    pub = EventPublisher()
    pub._eb_client = eb

    await pub.publish("comment_added", {"comment_id": "c1"})
    eb.put_events.assert_not_called()
