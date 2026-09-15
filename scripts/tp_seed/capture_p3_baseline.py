#!/usr/bin/env python3
"""Run the real pipeline-3 legacy scripts over the pinned fixture and record what they did.

This is the source side of pipeline-3 reconciliation. It runs the legacy
scripts **unmodified** -- reading their behaviour rather than reimplementing
it -- and writes one JSON observation per probe. The converted jobs are later
compared against these observations, never against a reimplementation of the
legacy and never against their own output.

Three things make this safe to run repeatedly.

*The legacy never touches the estate.* Every script is pointed at a generated
config that names clone buckets and the fixture's own namespace. The estate's
`otterworks-files`, and every table row outside the fixture namespace, are
untouched in every phase.

*The input is pinned before the legacy runs.* `gen_p3_fixture.py` has already
written an immutable snapshot. `storage_cleanup_daily.py` deletes the orphans
it finds and `analytics_daily.py` deletes the SQS batches it reads, so "run
the legacy, then point the target at the same input" would silently hand the
target a different input than the legacy saw. Both sides read the snapshot.

*Probes are isolated from each other.* Each one re-seeds its clone first, so
probe order cannot change probe results and re-running is meaningful.

The audit unit gets three probes rather than one, because
`audit_archive_weekly.py` behaves three different ways depending on the shape
of the record it finds, and only one of those shapes is what the audit-service
actually writes. See contract F-0.4 / F-0.4a / F-0.4b.

    capture_p3_baseline.py --ns p3probe --snapshot .migration/fixtures/p3/p3probe \\
        --out .migration/baselines/p3
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO = Path(__file__).resolve().parents[2]
LEGACY = REPO / "etl" / "scripts"

CFG_FILE_BUCKET = "otterworks-file-storage"
CFG_QUARANTINE_BUCKET = "otterworks-file-quarantine"
ARCHIVE_BUCKET = "otterworks-audit-archive"
DATA_LAKE_BUCKET = "otterworks-data-lake"
AUDIT_TABLE = "otterworks-audit-events"
ANALYTICS_TABLE = "otterworks-analytics-events"
ANALYTICS_QUEUE = "otterworks-analytics"

# analytics_daily.py:52 hardcodes the queue URL, account id and all:
#   https://sqs.us-east-1.amazonaws.com/123456789012/otterworks-analytics
# LocalStack derives the account from the access key, so a queue created with
# the usual `test` credentials lands under a different account and the legacy's
# receive_message 404s on it. Running the whole capture under this account id
# is what makes the hardcoded URL resolve. The legacy script is not touched,
# and the id is a placeholder from the source, not a real AWS account.
LOCALSTACK_ACCOUNT_ID = "123456789012"

# The legacy scripts read /opt/etl/config.ini and nothing else. Rather than
# patch them, the runner writes a throwaway config there. The values are
# LocalStack placeholders; no real credential is ever written to disk here, and
# the converted jobs read named secrets instead of this file at all.
CONFIG_PATH = Path("/opt/etl/config.ini")

CONFIG_TEMPLATE = """[aws]
access_key = {access_key}
secret_key = {secret_key}
region = {region}

[database]
host = localhost
port = 5432
database = otterworks_analytics
user = etl_user
password = {pg_password}

[services]
document_service_url = http://localhost:8083
file_service_url = http://localhost:8082
meilisearch_url = http://localhost:7700
meilisearch_api_key = {meili_key}

[s3]
data_lake_bucket = {data_lake}
file_storage_bucket = {file_bucket}
quarantine_bucket = {quarantine_bucket}
archive_bucket = {archive_bucket}
analytics_prefix = analytics/daily
"""


def _aws_kwargs() -> dict:
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint:
        return {}
    return {"endpoint_url": endpoint,
            "aws_access_key_id": LOCALSTACK_ACCOUNT_ID,
            "aws_secret_access_key": LOCALSTACK_ACCOUNT_ID}


def aws(service: str):
    return boto3.client(service, **_aws_kwargs())


def aws_resource(service: str):
    return boto3.resource(service, **_aws_kwargs())


def write_config() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(CONFIG_TEMPLATE.format(
        access_key=LOCALSTACK_ACCOUNT_ID if os.environ.get("AWS_ENDPOINT_URL")
        else os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        secret_key=LOCALSTACK_ACCOUNT_ID if os.environ.get("AWS_ENDPOINT_URL")
        else os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        pg_password=os.environ.get("P3_PG_PASSWORD", "unused-in-fixture-runs"),
        meili_key=os.environ.get("P3_MEILI_KEY", "unused-in-fixture-runs"),
        data_lake=DATA_LAKE_BUCKET,
        file_bucket=CFG_FILE_BUCKET,
        quarantine_bucket=CFG_QUARANTINE_BUCKET,
        archive_bucket=ARCHIVE_BUCKET,
    ))


def run_legacy(script: str) -> dict:
    """Run one legacy script and capture everything observable about the run."""
    started = datetime.now(tz=timezone.utc)
    proc = subprocess.run(
        [sys.executable, str(LEGACY / script)],
        capture_output=True, text=True, timeout=900,
        env={**os.environ, "TZ": "UTC", "LC_ALL": "C", "LANG": "C", "PYTHONHASHSEED": "0"},
    )
    return {
        "script": script,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "started_at": started.isoformat(),
        "duration_s": round((datetime.now(tz=timezone.utc) - started).total_seconds(), 3),
    }


def list_bucket(s3, bucket: str, prefix: str = "") -> list[dict]:
    out: list[dict] = []
    try:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append({"key": obj["Key"], "size": obj["Size"]})
    except ClientError:
        return []
    return sorted(out, key=lambda o: o["key"])


def empty_bucket(s3, bucket: str) -> None:
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})


def ensure_bucket(s3, name: str) -> None:
    try:
        s3.head_bucket(Bucket=name)
    except ClientError:
        s3.create_bucket(Bucket=name)


# ── storage cleanup ──────────────────────────────────────────────────────────


def capture_storage_cleanup(snapshot: Path, out: Path) -> dict:
    """Reseed the clone from the snapshot, run the legacy, diff what it removed.

    The delete set is derived from the *snapshot* minus what survived, so it is
    anchored to the pinned inventory rather than to whatever the job printed.
    """
    s3 = aws("s3")
    inventory = json.loads((snapshot / "file_inventory.json").read_text())
    expected = json.loads((snapshot / "expected_orphans.json").read_text())

    for bucket in (CFG_FILE_BUCKET, CFG_QUARANTINE_BUCKET):
        ensure_bucket(s3, bucket)
        empty_bucket(s3, bucket)
    for obj in inventory:
        s3.put_object(Bucket=CFG_FILE_BUCKET, Key=obj["key"], Body=b"\0" * min(obj["size"], 512))

    before = list_bucket(s3, CFG_FILE_BUCKET, "files/")
    result = run_legacy("storage_cleanup_daily.py")
    after = list_bucket(s3, CFG_FILE_BUCKET, "files/")
    quarantined = list_bucket(s3, CFG_QUARANTINE_BUCKET)

    survived = {o["key"] for o in after}
    deleted = sorted(o["key"] for o in before if o["key"] not in survived)
    expected_keys = sorted(o["key"] for o in expected)

    result.update({
        "objects_before": len(before),
        "objects_after": len(after),
        "deleted_keys": deleted,
        "quarantined_objects": quarantined,
        "expected_orphan_keys": expected_keys,
        "delete_set_matches_expected": deleted == expected_keys,
        # Sizes are recorded because the recon gate compares (key, size) pairs;
        # a key-only match would not catch a truncating copy.
        "deleted_with_size": [o for o in before if o["key"] not in survived],
    })
    (out / "p3-storage-cleanup.baseline.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


# ── audit archive: three shapes, three outcomes ──────────────────────────────


def capture_audit_archive(snapshot: Path, out: Path, ns: str) -> dict:
    """Run the legacy once per record shape against a table holding only that shape.

    Mixing the shapes in one table would hide the interesting result: the
    A-estate records would contribute nothing to a scan that the A-full records
    already satisfied, and the run would look like a success.
    """
    s3 = aws("s3")
    ddb = aws_resource("dynamodb")
    table = ddb.Table(AUDIT_TABLE)
    slices = json.loads((snapshot / "audit_events.json").read_text())
    ensure_bucket(s3, ARCHIVE_BUCKET)

    observations = {}
    for shape, rows in sorted(slices.items()):
        # Clear the fixture namespace, then load only this shape.
        scan_kwargs: dict = {"FilterExpression": "#n = :ns",
                             "ExpressionAttributeNames": {"#n": "ns"},
                             "ExpressionAttributeValues": {":ns": ns}}
        while True:
            resp = table.scan(**scan_kwargs)
            with table.batch_writer() as batch:
                for item in resp.get("Items", []):
                    batch.delete_item(Key={"id": item["id"]})
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

        with table.batch_writer() as batch:
            for item in rows:
                batch.put_item(Item=item)

        empty_bucket(s3, ARCHIVE_BUCKET)
        before_rows = table.scan(Select="COUNT")["Count"]
        result = run_legacy("audit_archive_weekly.py")
        after_rows = table.scan(Select="COUNT")["Count"]
        archive_objects = list_bucket(s3, ARCHIVE_BUCKET)

        result.update({
            "shape": shape,
            "records_seeded": len(rows),
            "rows_before": before_rows,
            "rows_after": after_rows,
            "rows_deleted_from_source": before_rows - after_rows,
            "archive_objects": archive_objects,
            "wrote_archive": any(o["key"].endswith(".jsonl.gz") for o in archive_objects),
            "wrote_compliance_report": any(
                "compliance" in o["key"] for o in archive_objects),
        })
        observations[shape] = result

    payload = {
        "kind": "p3-audit-baseline",
        "ns": ns,
        "observations": observations,
        # Restated here so a reader of the baseline alone can see whether the
        # run confirmed the contract or contradicted it.
        "contract_expectation": {
            "A-estate": "F-0.4: exit 0, no archive, no report, nothing deleted",
            "A-tsonly": "F-0.4b: archive written, then exit 1 on KeyError('event_id')",
            "A-full": "F-0.4a: archive written, deletes swallowed, nothing deleted",
        },
    }
    (out / "p3-audit-archive.baseline.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return payload


# ── analytics daily ──────────────────────────────────────────────────────────


def capture_analytics_daily(snapshot: Path, out: Path) -> dict:
    """Seed SQS + DynamoDB from the snapshot, run the legacy, read back its S3 output.

    The job drains the queue as it reads it (F-0.1), so the queue is recreated
    from the snapshot on every capture rather than topped up. Postgres is not
    reachable here and the legacy swallows that failure (C-2.16), so the run
    still exits 0 and still writes every S3 object; the swallowed error is part
    of what this baseline records.
    """
    s3, sqs, ddb = aws("s3"), aws("sqs"), aws_resource("dynamodb")
    dynamo_events = json.loads((snapshot / "analytics_dynamodb_events.json").read_text())
    sqs_events = json.loads((snapshot / "analytics_sqs_events.json").read_text())

    ensure_bucket(s3, DATA_LAKE_BUCKET)
    empty_bucket(s3, DATA_LAKE_BUCKET)

    sqs.create_queue(QueueName=ANALYTICS_QUEUE)
    queue_url = sqs.get_queue_url(QueueName=ANALYTICS_QUEUE)["QueueUrl"]
    sqs.purge_queue(QueueUrl=queue_url)
    for ev in sqs_events:
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(ev, sort_keys=True))

    table = ddb.Table(ANALYTICS_TABLE)
    with table.batch_writer() as batch:
        for ev in dynamo_events:
            batch.put_item(Item=ev)

    result = run_legacy("analytics_daily.py")

    objects = list_bucket(s3, DATA_LAKE_BUCKET)
    outputs = {}
    for obj in objects:
        body = s3.get_object(Bucket=DATA_LAKE_BUCKET, Key=obj["key"])["Body"].read()
        outputs[obj["key"]] = {
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "content": _decode_output(obj["key"], body),
        }

    summary = next((v["content"] for k, v in outputs.items() if k.endswith("summary.json.gz")), None)
    result.update({
        "sqs_seeded": len(sqs_events),
        "dynamodb_seeded": len(dynamo_events),
        "queue_remaining": int(sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"],
        )["Attributes"]["ApproximateNumberOfMessages"]),
        "sqs_poll_failed": "Too many SQS failures" in result["stdout"],
        "objects_written": sorted(outputs),
        "outputs": outputs,
        "summary": summary,
        "postgres_error_swallowed": "ERROR: PostgreSQL update failed" in result["stdout"],
    })
    (out / "p3-analytics-daily.baseline.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def _decode_output(key: str, body: bytes):
    raw = gzip.decompress(body) if key.endswith(".gz") else body
    text = raw.decode("utf-8")
    if key.endswith(".jsonl.gz"):
        return [json.loads(line) for line in text.splitlines() if line]
    return json.loads(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", required=True)
    ap.add_argument("--snapshot", required=True,
                    help="the immutable snapshot directory written by gen_p3_fixture.py")
    ap.add_argument("--out", default=".migration/baselines/p3")
    ap.add_argument("--only", choices=["analytics-daily", "storage-cleanup", "audit-archive"],
                    action="append")
    ap.add_argument("--allow-date-drift", action="store_true",
                    help="run even when the fixture's run_date is not today; "
                         "the cutoff boundary probes stop being boundary probes")
    args = ap.parse_args()

    snapshot = Path(args.snapshot)
    if not (snapshot / "manifest.json").exists():
        print(f"no fixture manifest under {snapshot}; run gen_p3_fixture.py first", file=sys.stderr)
        return 2

    manifest = json.loads((snapshot / "manifest.json").read_text())
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    if manifest["run_date"] != today and not args.allow_date_drift:
        # audit_archive_weekly.py and storage_cleanup_daily.py both derive their
        # date from datetime.now() with no parameter (P3-D08). If the fixture
        # was generated for a different day, the boundary probes sit somewhere
        # in the middle of the range and prove nothing, while still passing.
        print(f"fixture run_date is {manifest['run_date']} but today is {today}; "
              f"the legacy scripts date themselves from datetime.now(), so the "
              f"boundary probes would not be on the boundary. Regenerate the "
              f"fixture with --run-date {today}, or pass --allow-date-drift if "
              f"you only need the non-boundary behaviour.", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_config()

    wanted = set(args.only or ["analytics-daily", "storage-cleanup", "audit-archive"])
    summary: dict = {"kind": "p3-baseline-summary", "ns": args.ns,
                     "snapshot": str(snapshot), "captured": sorted(wanted),
                     "fixture_run_date": manifest["run_date"], "captured_on": today,
                     "audit_cutoff": manifest.get("audit_cutoff")}

    if "analytics-daily" in wanted:
        r = capture_analytics_daily(snapshot, out)
        summary["analytics_daily"] = {
            "exit_code": r["exit_code"],
            "objects_written": r["objects_written"],
            "summary": r["summary"],
            "postgres_error_swallowed": r["postgres_error_swallowed"],
        }
        print(f"analytics_daily.py: exit {r['exit_code']}, "
              f"{len(r['objects_written'])} S3 objects, "
              f"queue left with {r['queue_remaining']} of {r['sqs_seeded']} messages, "
              f"postgres error swallowed: {r['postgres_error_swallowed']}")

    if "storage-cleanup" in wanted:
        r = capture_storage_cleanup(snapshot, out)
        summary["storage_cleanup"] = {
            "exit_code": r["exit_code"],
            "deleted": len(r["deleted_keys"]),
            "matches_expected": r["delete_set_matches_expected"],
        }
        print(f"storage_cleanup_daily.py: exit {r['exit_code']}, "
              f"deleted {len(r['deleted_keys'])}, "
              f"matches expected orphan set: {r['delete_set_matches_expected']}")

    if "audit-archive" in wanted:
        p = capture_audit_archive(snapshot, out, args.ns)
        summary["audit_archive"] = {
            shape: {"exit_code": o["exit_code"], "wrote_archive": o["wrote_archive"],
                    "deleted": o["rows_deleted_from_source"]}
            for shape, o in p["observations"].items()
        }
        for shape, o in sorted(p["observations"].items()):
            print(f"audit_archive_weekly.py [{shape}]: exit {o['exit_code']}, "
                  f"archive written: {o['wrote_archive']}, "
                  f"source rows deleted: {o['rows_deleted_from_source']}")

    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
