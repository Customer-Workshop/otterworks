#!/usr/bin/env python3
"""Record the order the analytics source hands its events over, into the snapshot.

    AWS_ENDPOINT_URL=http://localhost:4566 \\
    python3 databricks/migration/p3/exports/capture_source_order.py \\
        --snapshot .migration/fixtures/p3/p3probe --run-date 2026-09-15

`analytics_daily.py` iterates `sqs_events + dynamo_events` in frame order and builds
`hourly_breakdown` and `top_users` as first-seen ordered dicts, so the order the source
returns is observable in the exported bytes. The SQS half is queue order, which the
snapshot file already preserves. The DynamoDB half is *scan* order, which is a property of
the table's own layout, not of the snapshot file: scanning the seeded fixture returns the
same 164 records the file holds, in a different sequence. Landing from file order therefore
produced correct counts and the wrong byte order.

This records the scan order once, next to the snapshot it belongs to, so the landing can
assign `ingest_ordinal` from what the source did rather than from how the file was written.
It only reads: it scans with the legacy's own filter expression and writes nothing back to
the estate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TABLE = "otterworks-analytics-events"
SNAPSHOT_FILE = "analytics_dynamodb_events.json"
ORDER_FILE = "analytics_source_order.json"


def resource():
    import boto3

    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint:
        raise SystemExit(
            "AWS_ENDPOINT_URL is unset. Without it boto3 resolves to whatever real account "
            "this session is authenticated to instead of the legacy estate; set it, e.g. "
            "AWS_ENDPOINT_URL=http://localhost:4566.")
    return boto3.resource("dynamodb", endpoint_url=endpoint,
                          aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "000000000000"),
                          aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY",
                                                               "000000000000"),
                          region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


def scan_order(table, run_date: str) -> list[str]:
    """The event ids the legacy's own scan returns, in the order it returns them."""
    ids, kwargs = [], {"FilterExpression": "begins_with(event_date, :ds)",
                       "ExpressionAttributeValues": {":ds": run_date}}
    while True:
        page = table.scan(**kwargs)
        ids += [item["event_id"] for item in page.get("Items", [])]
        last = page.get("LastEvaluatedKey")
        if not last:
            return ids
        kwargs["ExclusiveStartKey"] = last


def capture(snapshot: Path, run_date: str) -> dict:
    table = resource().Table(TABLE)
    first, second = scan_order(table, run_date), scan_order(table, run_date)
    if first != second:
        raise SystemExit(
            "two scans of the same table returned different orders, so the legacy's own "
            "output order is not reproducible and no recorded order can stand in for it")

    events = json.loads((snapshot / SNAPSHOT_FILE).read_text())
    held = {event["event_id"] for event in events}
    expected = {event["event_id"] for event in events
                if str(event.get("event_date", "")).startswith(run_date)}
    returned = [event_id for event_id in first if event_id in held]
    absent = expected - set(returned)
    if absent:
        raise SystemExit(
            f"{len(absent)} snapshot records dated {run_date} were not returned by the scan "
            f"(first: {min(absent)}); the table no longer holds the pinned input, so "
            "this order describes a different extraction than the one being landed.")

    # Records the estate gained after the snapshot was pinned are dropped rather than
    # sequenced: the legacy run being reproduced never saw them. Dropping them cannot
    # reorder the rest -- a scan returns items in the table's own layout order, so removing
    # one leaves the others in the same relative sequence.
    foreign = [event_id for event_id in first if event_id not in held]

    order = {"table": TABLE, "run_date": run_date, "event_ids": returned,
             "skipped_not_in_snapshot": foreign,
             "captured_at": datetime.now(timezone.utc).isoformat(),
             "scan_filter": "begins_with(event_date, :ds)"}
    (snapshot / ORDER_FILE).write_text(json.dumps(order, indent=2) + "\n")
    return {"snapshot": str(snapshot), "order_file": str(snapshot / ORDER_FILE),
            "events_ordered": len(returned), "skipped_not_in_snapshot": len(foreign), "reproducible_across_two_scans": True}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="the pinned input snapshot directory")
    ap.add_argument("--run-date", required=True, help="the day the legacy scan filters on")
    args = ap.parse_args(argv)
    json.dump(capture(Path(args.snapshot), args.run_date), sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    if (code := main()):
        raise SystemExit(code)
