#!/usr/bin/env python3
"""Seed the pipeline-3 probe fixture and pin an immutable input snapshot.

Pipeline 3's five Python jobs read four stores, and the estate provides none of
them in a shape the jobs can actually consume:

  - the SQS queue `otterworks-analytics` and the DynamoDB table
    `otterworks-analytics-events` are created by nothing (contract F-0.2);
  - `otterworks-file-storage` / `otterworks-file-quarantine` do not exist, the
    estate's file storage is `otterworks-files` (F-0.3);
  - the audit table holds records the archive job's scan filter cannot match,
    because the audit-service writes `Timestamp` and the job filters on
    `timestamp` (F-0.4);
  - `analytics_daily_summary` has no DDL anywhere.

So the fixture is built here rather than borrowed. It is deterministic by
construction (seeded RNG, fixed anchor, gzip `mtime=0`), and it covers the
adversarial clauses of the record contract on purpose: empty input, malformed
timestamps, absent event types, the full user-attribution precedence chain,
NULL attribution, and the three audit record shapes.

Two properties matter more than the data itself.

**Snapshot before mutation.** Two legacy jobs destroy their own input --
`storage_cleanup_daily.py` deletes every orphan it finds, and
`analytics_daily.py` deletes every SQS batch it reads. If the legacy ran first
and the target then read "the same input", the target would be reading what the
legacy left behind, and delete-set equality would be an artifact of ordering
rather than a fact about the two implementations. This script therefore writes
an immutable snapshot of every input *before* any legacy invocation, and that
snapshot -- not the live store -- is the declared input of both sides.

**Disjoint mutable state.** The legacy runs against `ow-tp-p3-legacy-<run>`, a
clone seeded from the snapshot. The estate's own buckets and tables are never
written by a legacy probe. Re-seeding is idempotent, so probe order cannot
change probe results.

    gen_p3_fixture.py --ns demo --run-date 2026-08-01 --out .migration/fixtures/p3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ANCHOR = datetime(2026, 8, 1, tzinfo=timezone.utc)
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DATA_LAKE_BUCKET = "otterworks-data-lake"
FILE_BUCKET_REAL = "otterworks-files"
FILE_METADATA_TABLE = "otterworks-file-metadata"
AUDIT_TABLE = "otterworks-audit-events"
ANALYTICS_TABLE = "otterworks-analytics-events"
ANALYTICS_QUEUE = "otterworks-analytics"

# Buckets etl/config.ini names but the estate does not create (F-0.3). The
# legacy clone is created under these names so the unmodified legacy script can
# run at all; the estate's own otterworks-files is never written.
CFG_FILE_BUCKET = "otterworks-file-storage"
CFG_QUARANTINE_BUCKET = "otterworks-file-quarantine"

RETENTION_DAYS = 90

# Two vocabularies, and they are not interchangeable (contract F-0.9).
#
# The event stream analytics_daily.py consumes comes from file-service
# (events.rs: `file_uploaded`, camelCase envelope with ownerId/fileId/sizeBytes)
# and document-service (`document_created`), so its `eventType ==
# "document_created"` comparisons are against snake_case values.
#
# The usage rollup consumes analytics-service's own events, whose EventType
# constants are dotted (`document.created`). Seeding one vocabulary into both
# would make one of the two units silently count zero of everything.
ETL_EVENT_TYPES = [
    "document_created", "document_edited", "document_deleted",
    "comment_added", "file_uploaded", "file_shared", "file_deleted",
]
# Every event type the rollup has a counter for, plus one it counts only into
# totalEvents (`document.shared`) and the ended half of the collab pair, which
# the aggregator does not count at all. Without both of those, a converted job
# that counted every event as a collab session, or that summed the counters
# into totalEvents, would reconcile green.
ANALYTICS_SERVICE_EVENT_TYPES = [
    "document.created", "document.edited", "document.viewed", "document.shared",
    "file.uploaded", "file.downloaded", "storage.allocated", "storage.released",
    "collab.session_started", "collab.session_ended",
]


# analytics_daily.py:52 hardcodes its queue URL including the account id, and
# LocalStack derives the account from the access key. Everything the legacy
# scripts will read has to live under that account or the hardcoded URL 404s.
# The id is a placeholder taken from the source, not a real AWS account.
LOCALSTACK_ACCOUNT_ID = "123456789012"


def _aws_kwargs() -> dict:
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint:
        raise SystemExit(
            "AWS_ENDPOINT_URL is unset. This generator seeds buckets and tables; "
            "without an endpoint boto3 resolves to whatever real account the session "
            "is authenticated to. Point it at the local estate, e.g. "
            "AWS_ENDPOINT_URL=http://localhost:4566.")
    return {"endpoint_url": endpoint,
            "aws_access_key_id": LOCALSTACK_ACCOUNT_ID,
            "aws_secret_access_key": LOCALSTACK_ACCOUNT_ID}


def aws(service: str):
    return boto3.client(service, **_aws_kwargs())


def aws_resource(service: str):
    return boto3.resource(service, **_aws_kwargs())


def det_id(rng: random.Random, prefix: str) -> str:
    return f"{prefix}-{rng.getrandbits(64):016x}"


def iso(dt: datetime) -> str:
    return dt.strftime(TS_FORMAT)


def rng_for(ns: str, part: str) -> random.Random:
    seed = int(hashlib.sha256(f"p3|{ns}|{part}".encode()).hexdigest()[:16], 16)
    return random.Random(seed)


# ── analytics events: the contract's adversarial cases, by construction ───────


def build_analytics_events(ns: str, run_date: str,
                           poison: bool = False) -> tuple[list[dict], list[dict]]:
    """(dynamodb_events, sqs_events) covering every clause in contract §2.

    The two sides are disjoint sets, because `analytics_daily.py` concatenates
    them and a shared event would make it impossible to tell a double-count bug
    from a correct union.
    """
    rng = rng_for(ns, "analytics")
    users = [det_id(rng, "usr") for _ in range(12)]
    docs = [det_id(rng, "doc") for _ in range(20)]
    files = [det_id(rng, "fil") for _ in range(15)]
    day = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    dynamo: list[dict] = []
    sqs: list[dict] = []

    def base(i: int, hour: int) -> dict:
        return {
            "event_id": det_id(rng, "evt"),
            "event_date": run_date,
            "timestamp": iso(day + timedelta(hours=hour, seconds=rng.randint(0, 3599))),
        }

    # Bulk of the day: ordinary, well-formed events spread across 24 hours, so
    # the hourly breakdown has real shape rather than a single bucket.
    for i in range(240):
        hour = rng.randrange(24)
        ev = base(i, hour)
        et = ETL_EVENT_TYPES[rng.randrange(len(ETL_EVENT_TYPES))]
        ev["eventType"] = et
        # Exercise the attribution precedence chain: ownerId wins over editedBy
        # wins over authorId wins over deletedBy wins over userId (C-2.6).
        attr = ["ownerId", "editedBy", "authorId", "deletedBy", "userId"][rng.randrange(5)]
        ev[attr] = users[rng.randrange(len(users))]
        if et.startswith("document") or et == "comment_added":
            ev["documentId"] = docs[rng.randrange(len(docs))]
        else:
            ev["fileId"] = files[rng.randrange(len(files))]
            if et == "file_uploaded":
                ev["sizeBytes"] = rng.randint(1024, 50_000_000)
        (dynamo if i % 3 else sqs).append(ev)

    probes: list[tuple[str, dict]] = [
        # event_type is copied to eventType only when eventType is absent (C-2.4).
        ("event-type-alias", {**base(900, 3), "event_type": "document_created",
                              "ownerId": users[0], "documentId": docs[0]}),
        # The dotted vocabulary analytics-service uses. It reaches the frame
        # and is counted in total_events and the hourly breakdown, but matches
        # none of the `== "document_created"` comparisons, so it contributes
        # nothing to documents_created or active_documents (F-0.9).
        ("dotted-type", {**base(906, 9), "eventType": "document.created",
                         "ownerId": users[0], "documentId": docs[6]}),
        # No type at all under either spelling -> "unknown" (C-2.4).
        ("no-type", {**base(901, 4), "ownerId": users[1], "documentId": docs[1]}),
        # No attribution column at all -> resolved_user_id "unknown", which is
        # excluded from active_users but present in top_users (C-2.7).
        ("no-attribution", {**base(902, 5), "eventType": "document_edited",
                            "documentId": docs[2]}),
        # Attribution present but empty string: the mask requires != "" as well
        # as notna(), so this must fall through to "unknown" (C-2.6).
        ("empty-attribution", {**base(903, 6), "eventType": "document_edited",
                               "ownerId": "", "documentId": docs[3]}),
        # Precedence: every column populated at once, ownerId must win (C-2.6).
        ("all-attribution", {**base(904, 7), "eventType": "document_edited",
                             "ownerId": users[2], "editedBy": users[3],
                             "authorId": users[4], "deletedBy": users[5],
                             "userId": users[6], "documentId": docs[4]}),
        # Malformed timestamp -> hour "00", not a crash (C-2.8).
        ("bad-timestamp", {"event_id": det_id(rng, "evt"), "event_date": run_date,
                           "timestamp": "not-a-timestamp", "eventType": "file_shared",
                           "userId": users[7], "fileId": files[0]}),
        # Absent timestamp -> hour "00" via the same fallback (C-2.8).
        ("no-timestamp", {"event_id": det_id(rng, "evt"), "event_date": run_date,
                          "eventType": "file_shared", "userId": users[8],
                          "fileId": files[1]}),
        # Z-suffixed offset: fromisoformat only accepts it after the replace,
        # so this proves the replace is load-bearing (C-2.8).
        ("zulu-timestamp", {"event_id": det_id(rng, "evt"), "event_date": run_date,
                            "timestamp": "2026-08-01T23:59:59Z",
                            "eventType": "file_uploaded", "ownerId": users[9],
                            "fileId": files[2], "sizeBytes": 4096}),
        # An event dated the day before: the DynamoDB scan filters on
        # begins_with(event_date, ds), so it must not appear (C-2.2).
        ("wrong-day", {"event_id": det_id(rng, "evt"),
                       "event_date": (day - timedelta(days=1)).strftime("%Y-%m-%d"),
                       "timestamp": iso(day - timedelta(hours=2)),
                       "eventType": "document_created", "ownerId": users[11],
                       "documentId": docs[5]}),
    ]

    if poison:
        # sizeBytes as a string. file-service types it u64 so the estate cannot
        # produce this, but the behaviour is worth pinning: pandas .sum() over a
        # mixed int/str column raises TypeError, the top-level handler catches
        # it, and the whole run exits 1 having written nothing (F-0.10). It is
        # opt-in because a single such record destroys every other observation
        # in the same run, which is exactly the point being recorded.
        probes.append(("string-size", {**base(905, 8), "eventType": "file_uploaded",
                                       "ownerId": users[10], "fileId": files[3],
                                       "sizeBytes": "2048"}))

    for i, (name, ev) in enumerate(probes):
        ev["_probe"] = name
        (dynamo if i % 2 else sqs).append(ev)

    return dynamo, sqs


# ── audit events: the three record shapes of F-0.4 ───────────────────────────


def build_audit_records(ns: str, run_date: str) -> dict[str, list[dict]]:
    """One slice per record shape. Which shape is 'the legacy behaviour' is not
    a matter of opinion -- it depends on who wrote the record, so all three are
    probed and none is treated as canonical.

      A-estate  as DynamoDbAuditRepository writes them: id, Id, Timestamp.
                The scan filter names `timestamp`, which these items do not
                have, and DynamoDB excludes items missing a filtered attribute.
                Expected: zero matches, exit 0, no archive, no report.
      A-tsonly  id + lowercase timestamp, no event_id. The archive uploads,
                then `event["event_id"]` raises KeyError outside the try.
                Expected: archive written, then exit 1.
      A-full    id + timestamp + event_id. Archive uploads, every delete fails
                on the id-only key schema and is swallowed.
                Expected: archive written, report written, deleted count 0.
    """
    rng = rng_for(ns, "audit")
    # audit_archive_weekly.py computes its cutoff from datetime.now(), not from
    # any parameter (F-0.4 / P3-D08), so the boundary probes are only on the
    # boundary when run_date is the day the legacy is actually invoked. The
    # capture runner checks this rather than letting it drift silently.
    run = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff = run - timedelta(days=RETENTION_DAYS)
    actions = ["document.view", "document.update", "file.download", "user.login"]

    def moments() -> list[tuple[str, datetime]]:
        # Boundary probes first: the filter is a strict `<` string compare, so
        # only cutoff-1s may be archived. Then a spread either side.
        out = [
            ("boundary-before", cutoff - timedelta(seconds=1)),
            ("boundary-exact", cutoff),
            ("boundary-after", cutoff + timedelta(seconds=1)),
        ]
        for i in range(40):
            out.append((f"old-{i:03d}", cutoff - timedelta(days=rng.randint(1, 200))))
        for i in range(15):
            out.append((f"recent-{i:03d}", cutoff + timedelta(days=rng.randint(1, 80))))
        return out

    # One moment list, shared by all three shapes. If each shape drew its own
    # random days the three runs would archive different record counts and the
    # comparison between them would be measuring the fixture, not the job.
    shared_moments = moments()

    slices: dict[str, list[dict]] = {}
    for shape in ("A-estate", "A-tsonly", "A-full"):
        rows = []
        for name, when in shared_moments:
            ident = f"{shape}-{name}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
            item: dict = {
                "id": ident,
                "ns": ns,
                "_probe": name,
                "_shape": shape,
                "UserId": det_id(rng, "usr"),
                "Action": actions[rng.randrange(len(actions))],
                "ResourceType": "document",
                "ResourceId": det_id(rng, "doc"),
            }
            if shape == "A-estate":
                # .NET round-trip "O" format, exactly as SaveEventAsync writes it.
                item["Id"] = ident
                item["Timestamp"] = when.strftime("%Y-%m-%dT%H:%M:%S.0000000+00:00")
            else:
                item["timestamp"] = iso(when)
                if shape == "A-full":
                    item["event_id"] = ident
            rows.append(item)
        slices[shape] = rows
    return slices


# ── file storage: the cleanup unit's orphan set ──────────────────────────────


def build_file_objects(ns: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(objects, metadata_rows, expected_orphans) on the file-service's real key convention.

    handlers.rs writes `files/{owner}/{file_id}`, which is what the cleanup
    job's `files/` prefix listing is actually looking at. The legacy seeder in
    testdata/legacy uses `{ns}/files/...` instead, which no service produces;
    following it here would make every object look orphaned and the delete set
    meaningless.
    """
    rng = rng_for(ns, "files")
    owners = [det_id(rng, "usr") for _ in range(8)]
    objects: list[dict] = []
    metadata: list[dict] = []

    for i in range(120):
        owner = owners[rng.randrange(len(owners))]
        file_id = det_id(rng, "fil")
        key = f"files/{owner}/{file_id}"
        # The declared size IS the body length. The cleanup recon compares
        # (key, size) pairs, so an object whose body is shorter than the size
        # the inventory claims would make every one of those pairs a fiction.
        size = rng.randint(128, 65_536)
        objects.append({"key": key, "size": size, "body": bytes([i % 251]) * size})
        metadata.append({
            "id": file_id, "ns": ns, "s3_key": key, "owner_id": owner,
            "size_bytes": size, "name": f"file-{i:05d}.bin",
            "mime_type": "application/octet-stream",
            "created_at": iso(ANCHOR - timedelta(hours=rng.randint(1, 720))),
        })

    # Orphans: objects with no metadata row. These are the expected delete set.
    orphans = []
    for i in range(17):
        owner = owners[rng.randrange(len(owners))]
        key = f"files/{owner}/{det_id(rng, 'orphan')}"
        size = rng.randint(128, 65_536)
        objects.append({"key": key, "size": size, "body": bytes([i % 251]) * size})
        orphans.append({"key": key, "size": size})

    # Metadata rows pointing at objects that do not exist. The legacy treats
    # referenced_keys as a set to subtract, so a dangling reference changes
    # nothing -- but it must not crash, and it must not resurrect an orphan.
    for i in range(5):
        owner = owners[rng.randrange(len(owners))]
        metadata.append({
            "id": det_id(rng, "fil"), "ns": ns,
            "s3_key": f"files/{owner}/{det_id(rng, 'missing')}",
            "owner_id": owner, "size_bytes": 1234, "name": f"dangling-{i}.bin",
            "mime_type": "application/octet-stream", "created_at": iso(ANCHOR),
        })

    # An object outside the files/ prefix: it is not listed, so it is neither
    # referenced nor orphaned, and must never enter the delete set.
    objects.append({"key": f"thumbnails/{det_id(rng, 'thumb')}", "size": 64, "body": b"x" * 64})

    objects.sort(key=lambda o: o["key"])
    orphans.sort(key=lambda o: o["key"])
    metadata.sort(key=lambda m: m["s3_key"])
    return objects, metadata, orphans


# ── usage events for the Scala rollup ────────────────────────────────────────


def build_usage_events(ns: str) -> list[dict]:
    """NDJSON in the exact shape `EventLoader` deserialises, with the
    byte-metadata edge cases the aggregator silently tolerates.

    `AnalyticsEvent` is a spray-json `jsonFormat7`, so every one of eventId,
    eventType, userId, resourceId, resourceType, metadata and timestamp must be
    present or the line fails to parse and the whole job dies. metadata is a
    `Map[String, String]`, so every value is a string, and the aggregator reads
    byte counts from `metadata("bytes")` and nowhere else -- allocated and
    released are distinguished by eventType, not by the key name
    (UsageRollupAggregator.storageBytes).

    The tolerated edges, all of which contribute zero without failing the day:
    a missing `bytes` key, a non-numeric value, and a negative value.
    """
    rng = rng_for(ns, "usage")
    users = [det_id(rng, "usr") for _ in range(10)]
    out = []
    for day_offset in range(7):
        day = ANCHOR - timedelta(days=day_offset)
        for _ in range(rng.randint(30, 90)):
            event_type = ANALYTICS_SERVICE_EVENT_TYPES[
                rng.randrange(len(ANALYTICS_SERVICE_EVENT_TYPES))]
            resource_type = event_type.split(".", 1)[0].replace("storage", "file")
            ev = {
                "eventId": det_id(rng, "uev"),
                "eventType": event_type,
                "userId": users[rng.randrange(len(users))],
                "resourceId": det_id(rng, "res"),
                "resourceType": resource_type,
                "metadata": {},
                "timestamp": iso(day + timedelta(seconds=rng.randint(0, 86399))),
            }
            roll = rng.random()
            if roll < 0.70:
                ev["metadata"] = {"bytes": str(rng.randint(1024, 10_000_000))}
            elif roll < 0.80:
                # Non-numeric: Try(...).getOrElse(0L) swallows it.
                ev["metadata"] = {"bytes": "not-a-number"}
            elif roll < 0.86:
                # Negative: parses, so it subtracts from the day's total.
                ev["metadata"] = {"bytes": str(-rng.randint(1, 4096))}
            elif roll < 0.93:
                # Present but no byte count at all.
                ev["metadata"] = {"source": "seed"}
            # else: empty metadata map
            out.append(ev)
    out.sort(key=lambda e: (e["timestamp"], e["eventId"]))
    return out


# ── provisioning ─────────────────────────────────────────────────────────────


def ensure_bucket(s3, name: str) -> None:
    try:
        s3.head_bucket(Bucket=name)
    except ClientError:
        s3.create_bucket(Bucket=name)


def ensure_table(ddb, name: str, key: str) -> None:
    existing = ddb.meta.client.list_tables()["TableNames"]
    if name in existing:
        return
    ddb.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    ).wait_until_exists()


def clear_ns(table, ns: str) -> int:
    """Delete this namespace's slice only. Never truncates the table."""
    key_name = table.key_schema[0]["AttributeName"]
    removed = 0
    kwargs: dict = {"FilterExpression": "#n = :ns",
                    "ExpressionAttributeNames": {"#n": "ns"},
                    "ExpressionAttributeValues": {":ns": ns}}
    while True:
        resp = table.scan(**kwargs)
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                batch.delete_item(Key={key_name: item[key_name]})
                removed += 1
        if "LastEvaluatedKey" not in resp:
            return removed
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", required=True)
    ap.add_argument("--run-date", default=ANCHOR.strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=".migration/fixtures/p3",
                    help="where the immutable input snapshot is written")
    ap.add_argument("--poison", action="store_true",
                    help="add the string-sizeBytes record (F-0.10). One of these "
                         "aborts the whole analytics run, so it belongs in its own "
                         "fixture, never in the one used for the parity baseline")
    ap.add_argument("--legacy-clone", action="store_true",
                    help="also provision the ow-tp-p3-legacy-* clone the legacy probes run against")
    args = ap.parse_args()

    ns, run_date = args.ns, args.run_date
    out = Path(args.out) / ns
    out.mkdir(parents=True, exist_ok=True)

    s3 = aws("s3")
    ddb = aws_resource("dynamodb")
    sqs = aws("sqs")

    dynamo_events, sqs_events = build_analytics_events(ns, run_date, poison=args.poison)
    audit_slices = build_audit_records(ns, run_date)
    file_objects, file_metadata, expected_orphans = build_file_objects(ns)
    usage_events = build_usage_events(ns)

    # ---- the snapshot, written before anything mutable is touched ----------
    def dump(name: str, payload) -> str:
        path = out / name
        body = json.dumps(payload, sort_keys=True, indent=2).encode()
        path.write_bytes(body)
        return hashlib.sha256(body).hexdigest()

    checksums = {
        "analytics_dynamodb_events.json": dump("analytics_dynamodb_events.json", dynamo_events),
        # The queue does not exist in this estate (F-0.2), so the SQS side is
        # pinned as a payload file. It stands in for the queue on both sides,
        # and the live-queue path is recorded as unverified rather than faked.
        "analytics_sqs_events.json": dump("analytics_sqs_events.json", sqs_events),
        "audit_events.json": dump("audit_events.json", audit_slices),
        "file_inventory.json": dump("file_inventory.json",
                                    [{"key": o["key"], "size": o["size"]} for o in file_objects]),
        "file_metadata.json": dump("file_metadata.json", file_metadata),
        "expected_orphans.json": dump("expected_orphans.json", expected_orphans),
        "usage_events.json": dump("usage_events.json", usage_events),
    }

    # NDJSON copy of the usage events, the shape the Scala job reads.
    ndjson = out / "usage-events.ndjson"
    ndjson.write_bytes(
        ("\n".join(json.dumps(e, sort_keys=True) for e in usage_events) + "\n").encode())
    checksums["usage-events.ndjson"] = hashlib.sha256(ndjson.read_bytes()).hexdigest()

    # ---- provision the stores ---------------------------------------------
    ensure_bucket(s3, DATA_LAKE_BUCKET)
    ensure_bucket(s3, FILE_BUCKET_REAL)
    ensure_table(ddb, ANALYTICS_TABLE, "event_id")
    ensure_table(ddb, AUDIT_TABLE, "id")
    ensure_table(ddb, FILE_METADATA_TABLE, "id")

    analytics_table = ddb.Table(ANALYTICS_TABLE)
    audit_table = ddb.Table(AUDIT_TABLE)
    metadata_table = ddb.Table(FILE_METADATA_TABLE)

    for t in (analytics_table, audit_table):
        clear_ns(t, ns)

    with analytics_table.batch_writer() as batch:
        for ev in dynamo_events:
            batch.put_item(Item={**ev, "ns": ns})
    with audit_table.batch_writer() as batch:
        for rows in audit_slices.values():
            for item in rows:
                batch.put_item(Item=item)
    with metadata_table.batch_writer() as batch:
        for row in file_metadata:
            batch.put_item(Item=row)

    queue_url = sqs.create_queue(QueueName=ANALYTICS_QUEUE)["QueueUrl"]

    # ---- the legacy's own clone, disjoint from the target's input ----------
    clone_buckets = {}
    if args.legacy_clone:
        # Named with the config.ini bucket names so the unmodified legacy
        # script can run; the estate's otterworks-files is never written.
        for bucket in (CFG_FILE_BUCKET, CFG_QUARANTINE_BUCKET):
            ensure_bucket(s3, bucket)
            clone_buckets[bucket] = 0
        # Re-seed from the snapshot every time, so probe order cannot leak.
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=CFG_FILE_BUCKET, Prefix="files/"):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=CFG_FILE_BUCKET, Delete={"Objects": keys})
        for obj in file_objects:
            s3.put_object(Bucket=CFG_FILE_BUCKET, Key=obj["key"], Body=obj["body"])
            clone_buckets[CFG_FILE_BUCKET] += 1

    manifest = {
        "kind": "p3-fixture-manifest",
        "ns": ns,
        "run_date": run_date,
        "anchor": iso(ANCHOR),
        "retention_days": RETENTION_DAYS,
        "snapshot_dir": str(out),
        "checksums": checksums,
        "counts": {
            "analytics_dynamodb": len(dynamo_events),
            "analytics_sqs": len(sqs_events),
            "audit_A-estate": len(audit_slices["A-estate"]),
            "audit_A-tsonly": len(audit_slices["A-tsonly"]),
            "audit_A-full": len(audit_slices["A-full"]),
            "file_objects": len(file_objects),
            "expected_orphans": len(expected_orphans),
            "usage_events": len(usage_events),
        },
        "audit_cutoff": iso(datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            - timedelta(days=RETENTION_DAYS)),
        "expected": {
            "audit": {
                "A-estate": "scan matches 0 (filter names `timestamp`, records carry `Timestamp`); exit 0; no archive object, no compliance report",
                "A-tsonly": "archive uploaded, then KeyError on event_id at :141 (outside the try) -> exit 1",
                "A-full": "archive uploaded, all deletes fail on the id-only key schema and are swallowed, events_deleted_from_source = 0",
            },
            "storage_cleanup": {
                "delete_set": "expected_orphans.json, compared as a set of (key, size)",
                "not_in_delete_set": "objects outside the files/ prefix, and objects with a live metadata row",
                "dangling_metadata": "5 metadata rows point at absent objects; they subtract nothing and must not crash the job",
            },
        },
        "stores": {
            "analytics_table": ANALYTICS_TABLE,
            "audit_table": AUDIT_TABLE,
            "file_metadata_table": FILE_METADATA_TABLE,
            "sqs_queue_url": queue_url,
            "legacy_clone_buckets": clone_buckets,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")

    print(f"p3 fixture: ns={ns} run_date={run_date} -> {out}")
    for k, v in manifest["counts"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
