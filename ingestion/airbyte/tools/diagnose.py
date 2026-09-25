"""Print the most recent non-green job on an Airbyte connection and what the public API says about it.

The Airbyte public API (api.airbyte.com/v1) exposes job status, timings and
row/byte counts but not attempt logs or the failure reason. This tool prints
what it can read, then tells the operator where the reason lives (the job's
"View logs" in the Cloud UI) and how to check whether the source configuration
drifted from Terraform.

Environment: AIRBYTE_CLIENT_ID, AIRBYTE_CLIENT_SECRET, AIRBYTE_CONNECTION_ID (or --connection-id).

Usage:
  diagnose.py --connection-id <id> [--limit 20] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
from sync_and_recon import Airbyte

NON_GREEN = {"failed", "cancelled", "incomplete"}
SECRET_KEYS = ("aws_secret_access_key", "aws_access_key_id", "secret", "token", "password", "credentials")


def redact(value):
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if any(s in k.lower() for s in SECRET_KEYS) else redact(v))
            for k, v in value.items()
            if k != "streams"
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--connection-id", default=os.getenv("AIRBYTE_CONNECTION_ID"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="print the raw job records instead of a summary")
    args = parser.parse_args()
    if not args.connection_id:
        parser.error("--connection-id or AIRBYTE_CONNECTION_ID is required")

    airbyte = Airbyte()
    query = urllib.parse.urlencode(
        {"connectionId": args.connection_id, "limit": args.limit, "orderBy": "createdAt|DESC"}
    )
    status, body = airbyte.call("GET", f"/jobs?{query}")
    if status != 200:
        raise SystemExit(f"airbyte list jobs: HTTP {status} {body}")
    jobs = body.get("data", [])
    if args.json:
        print(json.dumps(redact(jobs), indent=2))
        return 0
    latest_is_green = bool(jobs) and jobs[0]["status"] == "succeeded"

    print(f"connection {args.connection_id}: last {len(jobs)} jobs (newest first)")
    for job in jobs:
        print(
            f"  {job['jobId']}  {job['status']:<10} start={job.get('startTime')}  "
            f"duration={job.get('duration')}  rows={job.get('rowsSynced')}  bytes={job.get('bytesSynced')}"
        )

    bad = next((j for j in jobs if j["status"] in NON_GREEN), None)
    if bad is None:
        print("no failed/cancelled/incomplete job in this window")
        if not latest_is_green:
            print(f"latest job is {jobs[0]['status'] if jobs else 'absent'}, not succeeded")
        return 0 if latest_is_green else 1

    status, detail = airbyte.call("GET", f"/jobs/{bad['jobId']}")
    print(f"\nlast non-green job: {bad['jobId']} ({bad['status']})")
    print(json.dumps(redact(detail if status == 200 else {"http": status, "body": detail}), indent=2))
    print(
        "\nThe public API does not return attempt logs or a failure reason. Read them in the Cloud UI:\n"
        f"  connection -> Timeline -> job {bad['jobId']} -> View logs / Download logs\n"
        "Then check the source against Terraform. Airbyte masks credentials on read, so `terraform plan`\n"
        "cannot see a rotated secret; re-import the source to force the comparison:\n"
        "  make tp-airbyte-repair NS=<ns>"
    )

    status, conn = airbyte.call("GET", f"/connections/{args.connection_id}")
    if status == 200:
        status, source = airbyte.call("GET", f"/sources/{conn['sourceId']}")
        if status == 200:
            print(f"\nsource {source['sourceId']} ({source['name']}) non-secret configuration:")
            print(json.dumps(redact(source.get("configuration", {})), indent=2))
    print("\nexit status: 0 only when the newest job in the window succeeded")
    if latest_is_green:
        print(f"\nlatest job {jobs[0]['jobId']} succeeded; the connection has recovered")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
