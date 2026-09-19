import json
import logging
import math
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import NAMESPACE_URL, uuid5

import boto3
import requests

LOGGER = logging.getLogger("usage-bridge")
QUEUE_NAME = "otterworks-billing-usage"
TOPIC_ARN = os.getenv(
    "SNS_TOPIC_ARN",
    "arn:aws:sns:us-east-1:000000000000:otterworks-events",
)
LEGACY_BILLING_URL = os.getenv("LEGACY_BILLING_URL", "http://legacy-billing:8096")
USAGE_PATH = "/internal/usage/events"
SUPPORTED_EVENTS = {
    "document_created": ("api", 1),
    "document_updated": ("api", 1),
    "comment_added": ("api", 1),
    "file_uploaded": ("storage", 1),
    "file_updated": ("compute", 1),
}


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {
            "received": 0,
            "recorded": 0,
            "duplicate": 0,
            "skipped": 0,
            "rejected": 0,
            "deferred": 0,
        }

    def increment(self, name):
        with self._lock:
            self._counts[name] += 1

    def snapshot(self):
        with self._lock:
            return dict(self._counts)


def _event_fields(event):
    event_type = event.get("event_type") or event.get("eventType")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
    entity_id = (
        payload.get("id")
        or payload.get("file_id")
        or payload.get("fileId")
        or payload.get("comment_id")
        or payload.get("commentId")
    )
    tenant_id = payload.get("owner_id") or payload.get("ownerId")
    timestamp = event.get("timestamp") or payload.get("timestamp")
    return event_type, payload, entity_id, tenant_id, timestamp


def map_event(event):
    event_type, payload, entity_id, tenant_id, timestamp = _event_fields(event)
    if event_type not in SUPPORTED_EVENTS or not entity_id or not tenant_id or not timestamp:
        return None

    kind, units = SUPPORTED_EVENTS[event_type]
    if event_type == "file_uploaded":
        size_bytes = payload.get("size_bytes", payload.get("sizeBytes", 0)) or 0
        units = max(1, math.ceil(int(size_bytes) / 1_048_576))
        kind = "storage"
    event_id = str(uuid5(NAMESPACE_URL, f"ow-usage:{event_type}:{entity_id}:{timestamp}"))
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "email": None,
        "kind": kind,
        "units": units,
        "occurred_at": timestamp,
    }


def deterministic_event_id(event_type, entity_id, timestamp):
    return str(uuid5(NAMESPACE_URL, f"ow-usage:{event_type}:{entity_id}:{timestamp}"))


class HealthHandler(BaseHTTPRequestHandler):
    metrics = None

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps(self.metrics.snapshot()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class UsageBridge:
    def __init__(
        self,
        sqs_client=None,
        sns_client=None,
        http_session=None,
        legacy_url=LEGACY_BILLING_URL,
        metrics=None,
    ):
        region = os.getenv("AWS_REGION", "us-east-1")
        endpoint = os.getenv("AWS_ENDPOINT_URL")
        client_kwargs = {"region_name": region}
        if endpoint:
            client_kwargs["endpoint_url"] = endpoint
        self.sqs = sqs_client or boto3.client("sqs", **client_kwargs)
        self.sns = sns_client or boto3.client("sns", **client_kwargs)
        self.http = http_session or requests.Session()
        self.legacy_url = legacy_url.rstrip("/")
        self.metrics = metrics or Metrics()
        self.queue_url = None

    def setup(self):
        queue = self.sqs.create_queue(
            QueueName=QUEUE_NAME,
            Attributes={"VisibilityTimeout": "30"},
        )
        self.queue_url = queue["QueueUrl"]
        queue_attributes = self.sqs.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=["QueueArn"],
        )["Attributes"]
        queue_arn = queue_attributes["QueueArn"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "AllowSnsDelivery",
                "Effect": "Allow",
                "Principal": {"Service": "sns.amazonaws.com"},
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": TOPIC_ARN}},
            }],
        }
        self.sqs.set_queue_attributes(
            QueueUrl=self.queue_url,
            Attributes={"Policy": json.dumps(policy)},
        )
        subscriptions = self.sns.list_subscriptions_by_topic(
            TopicArn=TOPIC_ARN,
        ).get("Subscriptions", [])
        subscription_arn = next(
            (
                subscription["SubscriptionArn"]
                for subscription in subscriptions
                if subscription.get("Endpoint") == queue_arn
            ),
            None,
        )
        if not subscription_arn:
            subscription_arn = self.sns.subscribe(
                TopicArn=TOPIC_ARN,
                Protocol="sqs",
                Endpoint=queue_arn,
                ReturnSubscriptionArn=True,
            )["SubscriptionArn"]
        self.sns.set_subscription_attributes(
            SubscriptionArn=subscription_arn,
            AttributeName="RawMessageDelivery",
            AttributeValue="true",
        )

    def process_message(self, message):
        self.metrics.increment("received")
        try:
            event = json.loads(message["Body"])
        except (KeyError, TypeError, json.JSONDecodeError):
            self.metrics.increment("skipped")
            return True
        usage = map_event(event)
        if usage is None:
            self.metrics.increment("skipped")
            return True
        try:
            response = self.http.post(
                f"{self.legacy_url}{USAGE_PATH}",
                json=usage,
                timeout=10,
            )
        except requests.RequestException:
            self.metrics.increment("deferred")
            return False
        if response.status_code in (200, 201):
            status = (response.json() if response.content else {}).get("status")
            self.metrics.increment("duplicate" if status == "duplicate" else "recorded")
            return True
        if response.status_code == 422:
            LOGGER.warning("usage rejected by legacy billing")
            self.metrics.increment("rejected")
            return True
        if response.status_code in (502, 503, 504) or response.status_code >= 500:
            self.metrics.increment("deferred")
            return False
        self.metrics.increment("rejected")
        return True

    def run_once(self):
        response = self.sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=10,
        )
        deferred = False
        for message in response.get("Messages", []):
            if self.process_message(message):
                self.sqs.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
            else:
                deferred = True
        if deferred:
            LOGGER.warning("usage batch deferred; messages remain queued")

    def run(self):
        self.setup()
        while True:
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("usage bridge receive loop failed")


def start_health_server(metrics, port=8097):
    HealthHandler.metrics = metrics
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    bridge = UsageBridge()
    start_health_server(bridge.metrics)
    bridge.run()
