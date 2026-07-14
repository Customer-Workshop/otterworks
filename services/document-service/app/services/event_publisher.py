"""SNS event publishing for domain events."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from app.config import settings

logger = structlog.get_logger()


class _UUIDEncoder(json.JSONEncoder):
    def default(self, o: object) -> Any:
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


class EventPublisher:
    """Publishes domain events to AWS.

    Two interchangeable backends, selected by ``settings.event_backend``:
      * ``sns`` (default) — publish to the SNS topic fanned out to the SQS queue
        drained by the in-cluster notification consumer. This is the golden-app
        path on ``main`` and is unchanged.
      * ``eventbridge`` — ``PutEvents`` to a custom EventBridge bus whose rule
        routes to an SQS queue drained by a serverless Lambda consumer.

    The event body is byte-identical across backends; only the transport differs,
    so the two consumer paths are behavior-identical.
    """

    def __init__(self) -> None:
        self._client = None
        self._eb_client = None

    def _get_client(self):  # noqa: ANN202
        if self._client is None:
            import boto3

            kwargs = {"region_name": settings.aws_region}
            if settings.aws_endpoint_url:
                kwargs["endpoint_url"] = settings.aws_endpoint_url
            self._client = boto3.client("sns", **kwargs)
        return self._client

    def _get_eventbridge_client(self):  # noqa: ANN202
        if self._eb_client is None:
            import boto3

            kwargs = {"region_name": settings.aws_region}
            if settings.aws_endpoint_url:
                kwargs["endpoint_url"] = settings.aws_endpoint_url
            self._eb_client = boto3.client("events", **kwargs)
        return self._eb_client

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        message_body = json.dumps(message, cls=_UUIDEncoder)

        if settings.event_backend == "eventbridge":
            await self._publish_eventbridge(event_type, message_body)
            return

        if not settings.sns_enabled:
            logger.info("sns_event_skipped", event_type=event_type)
            return

        try:
            client = self._get_client()
            await asyncio.to_thread(
                client.publish,
                TopicArn=settings.sns_topic_arn,
                Message=message_body,
                MessageAttributes={
                    "event_type": {"DataType": "String", "StringValue": event_type}
                },
            )
            logger.info("sns_event_published", event_type=event_type)
        except Exception:
            logger.exception("sns_publish_failed", event_type=event_type)

    async def _publish_eventbridge(self, event_type: str, message_body: str) -> None:
        if not settings.eventbridge_bus_name:
            logger.info("eventbridge_event_skipped", event_type=event_type)
            return

        try:
            client = self._get_eventbridge_client()
            await asyncio.to_thread(
                client.put_events,
                Entries=[
                    {
                        "EventBusName": settings.eventbridge_bus_name,
                        "Source": settings.eventbridge_source,
                        "DetailType": event_type,
                        "Detail": message_body,
                    }
                ],
            )
            logger.info("eventbridge_event_published", event_type=event_type)
        except Exception:
            logger.exception("eventbridge_publish_failed", event_type=event_type)


event_publisher = EventPublisher()
