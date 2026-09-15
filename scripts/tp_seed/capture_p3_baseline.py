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
import contextlib
import fcntl
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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

# analytics_daily.py hardcodes its queue URL and every script reads the one
# global config path, so two captures on the same host cannot be given disjoint
# resources -- one would purge the queue, empty the clone buckets or rewrite the
# config under the other's legacy process. They are serialised instead.
LOCK_PATH = Path(os.environ.get("P3_CAPTURE_LOCK", "/tmp/otterworks-p3-capture.lock"))

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
        raise SystemExit(
            "AWS_ENDPOINT_URL is unset. This capture seeds buckets and tables and runs "
            "the legacy scripts against them; without an endpoint boto3 resolves to "
            "whatever real account the session is authenticated to. Point it at the "
            "local estate, e.g. AWS_ENDPOINT_URL=http://localhost:4566.")
    return {"endpoint_url": endpoint,
            "aws_access_key_id": LOCALSTACK_ACCOUNT_ID,
            "aws_secret_access_key": LOCALSTACK_ACCOUNT_ID}


def aws(service: str):
    return boto3.client(service, **_aws_kwargs())


def aws_resource(service: str):
    return boto3.resource(service, **_aws_kwargs())


@contextlib.contextmanager
def capture_lock():
    """Exclusive host-wide lock over reset, seed, legacy run and observation."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"another p3 capture holds {LOCK_PATH}; waiting for it to finish",
                  file=sys.stderr)
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def fixture_config():
    """Install the fixture config at the one path the legacy reads, then put back
    whatever was there.

    The legacy scripts read /opt/etl/config.ini and nothing else, so the capture
    has to replace a global file. Leaving the fixture version installed would
    point the next legacy invocation on this host at clone buckets and a
    placeholder database, so the original bytes, permissions and ownership are
    restored on every exit path, and a file this runner created is removed again.

    Replacing the file gives the new copy this process's ownership, and an
    unprivileged caller can only hand it back to itself and to a group it is a
    member of. A config it could not fully restore is therefore refused before
    it is touched: finishing the capture at the cost of leaving the host's ETL
    config unreadable by the account or group that owns it is not a trade this
    runner gets to make.
    """
    existed = CONFIG_PATH.exists()
    original = CONFIG_PATH.read_bytes() if existed else None
    st = CONFIG_PATH.stat() if existed else None
    if st is not None and os.geteuid() != 0 and (
            st.st_uid != os.geteuid() or st.st_gid not in {os.getegid(), *os.getgroups()}):
        raise SystemExit(
            f"{CONFIG_PATH} is owned by {st.st_uid}:{st.st_gid}, which uid "
            f"{os.geteuid()} cannot restore: the capture would replace it and then "
            f"fail to give it back, and its owners would lose access. Re-run as its "
            f"owner with membership of that group, or as root.")
    try:
        write_config()
        yield
    finally:
        if existed:
            restore_file(CONFIG_PATH, original, st)
        else:
            CONFIG_PATH.unlink(missing_ok=True)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Replace `path` in one step, so no reader ever sees a half-written config."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def restore_file(path: Path, data: bytes, st: os.stat_result) -> None:
    """Put a file back exactly as it was found: bytes, permissions and ownership."""
    atomic_write(path, data, st.st_mode & 0o777)
    try:
        os.chown(path, st.st_uid, st.st_gid)
    except PermissionError:
        raise SystemExit(
            f"restored the contents of {path} but could not give it back to "
            f"{st.st_uid}:{st.st_gid}; it is now owned by uid {os.geteuid()} and the "
            f"original owner may no longer be able to read it. Fix the ownership "
            f"before running anything else on this host.") from None


def foreign_rows(table, scan_kwargs: dict, seeded: set[str]) -> list[str]:
    """Key values the legacy's own scan would read that this capture did not seed.

    The fixture tables are shared, and no legacy scan filters by namespace: the
    analytics job takes every row for the run date and the audit job every row
    below its cutoff. A leftover row from another namespace would be aggregated
    into the baseline and become source-side evidence for the migration, with
    the capture exiting 0 and every behavioural assertion still passing. So the
    input is checked for identity, not just the output for plausibility.
    """
    key_name = table.key_schema[0]["AttributeName"]
    extra, kwargs = [], dict(scan_kwargs)
    while True:
        resp = table.scan(**kwargs)
        extra += [item[key_name] for item in resp.get("Items", [])
                  if item[key_name] not in seeded]
        if "LastEvaluatedKey" not in resp:
            return sorted(extra)
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def require_isolated(table, scan_kwargs: dict, seeded: set[str], what: str) -> None:
    extra = foreign_rows(table, scan_kwargs, seeded)
    if extra:
        raise SystemExit(
            f"{table.name} holds {len(extra)} row(s) that {what} would read and this "
            f"capture did not seed, e.g. {extra[:5]}. They would be aggregated into the "
            f"baseline. Clear the other namespace's rows for this window, or capture "
            f"against a table no other run shares.")


def verify_snapshot(snapshot: Path, manifest: dict) -> None:
    """Re-hash every declared snapshot input before anything mutable is touched.

    The manifest carries a SHA-256 per input. Without checking them, an edited
    `expected_orphans.json` or a file left over from an earlier generation is
    frozen into the baseline under the original snapshot's identity.
    """
    checksums = manifest.get("checksums")
    if not checksums:
        raise SystemExit(f"{snapshot}/manifest.json carries no checksums; regenerate the fixture")
    problems = []
    for name, expected in sorted(checksums.items()):
        path = snapshot / name
        if not path.exists():
            problems.append(f"{name}: declared in the manifest but missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"{name}: sha256 {actual} != manifest {expected}")
    if problems:
        raise SystemExit("snapshot does not match its manifest:\n  " + "\n  ".join(problems))


def write_config() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(CONFIG_PATH, CONFIG_TEMPLATE.format(
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
    ).encode())


def run_legacy(script: str) -> dict:
    """Run one legacy script and capture everything observable about the run."""
    started = datetime.now(tz=timezone.utc)
    proc = subprocess.run(
        [sys.executable, str(LEGACY / script)],
        capture_output=True, text=True, timeout=900, check=False,
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


def read_archive_records(s3, bucket: str, key: str) -> list[dict]:
    """The archived bodies themselves, not just the object's size.

    The recon compares the rows the legacy archived, so the baseline has to
    carry them. Only the object listing survived the first capture, and each
    probe overwrites the previous probe's object, so the contents are read back
    inside the probe rather than recovered afterwards.
    """
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except s3.exceptions.InvalidObjectState:
        # The legacy writes the archive as GLACIER, which is not readable in place.
        s3.restore_object(Bucket=bucket, Key=key,
                          RestoreRequest={"Days": 1,
                                          "GlacierJobParameters": {"Tier": "Expedited"}})
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    lines = gzip.decompress(body).decode("utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


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
    # The body is exactly the size the inventory declares. A shorter body would
    # still satisfy a key-only comparison while making every (key, size) pair
    # in this baseline -- and in the recon that reads it -- a fiction.
    for obj in inventory:
        s3.put_object(Bucket=CFG_FILE_BUCKET, Key=obj["key"], Body=b"\0" * obj["size"])

    before = list_bucket(s3, CFG_FILE_BUCKET, "files/")
    declared = {o["key"]: o["size"] for o in inventory}
    seeded_mismatch = [
        {"key": o["key"], "declared": declared[o["key"]], "stored": o["size"]}
        for o in before
        if declared.get(o["key"], o["size"]) != o["size"]
    ]

    result = run_legacy("storage_cleanup_daily.py")
    after = list_bucket(s3, CFG_FILE_BUCKET, "files/")
    quarantined = list_bucket(s3, CFG_QUARANTINE_BUCKET)

    survived = {o["key"] for o in after}
    deleted = sorted((o for o in before if o["key"] not in survived), key=lambda o: o["key"])
    expected_pairs = sorted(({"key": o["key"], "size": o["size"]} for o in expected),
                            key=lambda o: o["key"])

    result.update({
        "objects_before": len(before),
        "objects_after": len(after),
        "deleted_keys": [o["key"] for o in deleted],
        "quarantined_objects": quarantined,
        "expected_orphan_keys": [o["key"] for o in expected_pairs],
        # The gate is the (key, size) set, not the key set: a truncating copy
        # deletes the right keys and still loses data.
        "deleted_with_size": deleted,
        "expected_orphans_with_size": expected_pairs,
        "delete_set_matches_expected": deleted == expected_pairs,
        "seeded_size_mismatches": seeded_mismatch,
    })
    (out / "p3-storage-cleanup.baseline.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


# ── audit archive: three shapes, three outcomes ──────────────────────────────


def capture_audit_archive(snapshot: Path, out: Path, ns: str, cutoff: str) -> dict:
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

        require_isolated(
            table,
            {"FilterExpression": "#ts < :cutoff",
             "ExpressionAttributeNames": {"#ts": "timestamp"},
             "ExpressionAttributeValues": {":cutoff": cutoff}},
            {item["id"] for item in rows},
            "audit_archive_weekly.py")

        empty_bucket(s3, ARCHIVE_BUCKET)
        before_rows = table.scan(Select="COUNT")["Count"]
        result = run_legacy("audit_archive_weekly.py")
        after_rows = table.scan(Select="COUNT")["Count"]
        archive_objects = list_bucket(s3, ARCHIVE_BUCKET)

        archived_records: list[dict] = []
        report: dict | None = None
        for obj in archive_objects:
            if obj["key"].endswith(".jsonl.gz"):
                archived_records = read_archive_records(s3, ARCHIVE_BUCKET, obj["key"])
            elif "compliance" in obj["key"]:
                report = json.loads(
                    s3.get_object(Bucket=ARCHIVE_BUCKET, Key=obj["key"])["Body"].read())

        result.update({
            "shape": shape,
            "archived_records": archived_records,
            "compliance_report": report,
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


def capture_analytics_daily(snapshot: Path, out: Path, ns: str,
                            filename: str = "p3-analytics-daily.baseline.json") -> dict:
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
    # The legacy partitions on datetime.now(UTC), not on the fixture's run_date,
    # and the two differ under --allow-date-drift. The isolation check has to
    # scan the day the legacy will scan, or a foreign row dated today walks into
    # the baseline unseen.
    scan_date = legacy_analytics_date()

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
            batch.put_item(Item={**ev, "ns": ns})

    require_isolated(
        table,
        {"FilterExpression": "begins_with(event_date, :ds)",
         "ExpressionAttributeValues": {":ds": scan_date}},
        {ev["event_id"] for ev in dynamo_events},
        "analytics_daily.py")

    result = run_legacy("analytics_daily.py")

    if legacy_analytics_date() != scan_date:
        raise SystemExit(
            f"the UTC date rolled from {scan_date} to {legacy_analytics_date()} during "
            f"the capture, so analytics_daily.py did not read the day the isolation "
            f"check inspected. Re-run it.")

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
    (out / filename).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


# ── user activity: the one unit that reads another unit's output ─────────────


PG_DSN = {"host": "localhost", "port": 5432, "dbname": "otterworks_analytics",
          "user": "etl_user"}

SUMMARY_COLUMNS = ["report_date", "active_users", "active_documents", "active_files",
                   "total_events", "documents_created", "documents_edited",
                   "comments_added", "files_uploaded", "files_shared",
                   "files_deleted", "bytes_uploaded"]


def pg_connect():
    """Connect to the local fixture serving database, by env var, never by literal."""
    import psycopg2
    password = os.environ.get("P3_PG_PASSWORD")
    if not password:
        raise SystemExit(
            "P3_PG_PASSWORD is unset. user_activity_daily.py exits 1 when its Postgres "
            "query fails (:117), so without the serving database there is no baseline "
            "to capture -- only a failed run.")
    return psycopg2.connect(**PG_DSN, password=password)


def seed_summary_history(conn, days: list[dict], window: list[str]) -> dict:
    """Put the history's summary rows in the table the legacy reads, and prove that
    the window holds nothing else.

    The legacy's query is a date range with no namespace or job filter, so any other
    row inside the window is read as if this capture had produced it and lands in the
    baseline's trends. The window is checked for identity before the legacy runs.
    """
    seeded = {d["summary"]["report_date"] for d in days}
    with conn.cursor() as cur:
        cur.execute("DELETE FROM analytics_daily_summary WHERE report_date = ANY(%s::date[])",
                    (sorted(seeded),))
        for day in days:
            s = day["summary"]
            cur.execute(
                "INSERT INTO analytics_daily_summary (" + ", ".join(SUMMARY_COLUMNS) +
                ", updated_at) VALUES (" + ", ".join(["%s"] * len(SUMMARY_COLUMNS)) +
                ", NOW()) ON CONFLICT (report_date) DO UPDATE SET " +
                ", ".join(f"{c} = EXCLUDED.{c}" for c in SUMMARY_COLUMNS[1:]),
                [s[c] for c in SUMMARY_COLUMNS])
        conn.commit()
        cur.execute(
            "SELECT report_date FROM analytics_daily_summary "
            "WHERE report_date BETWEEN %s AND %s ORDER BY report_date",
            (window[0], window[1]))
        in_window = [r[0].isoformat() for r in cur.fetchall()]
    return {"seeded_dates": sorted(seeded), "window": window, "dates_in_window": in_window}


def seed_top_user_history(s3, days: list[dict]) -> list[str]:
    """Write each history day's top_users.jsonl.gz where the legacy looks for it.

    Same bytes the analytics job writes for the run date: one JSON object per line,
    gzip with mtime=0 so the object is byte-identical on every re-seed.
    """
    keys = []
    for day in days:
        y, m, d = day["date"].split("-")
        key = f"analytics/daily/year={y}/month={m}/day={d}/top_users.jsonl.gz"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            for row in day["top_users"]:
                gz.write(json.dumps(row).encode("utf-8"))
                gz.write(b"\n")
        s3.put_object(Bucket=DATA_LAKE_BUCKET, Key=key, Body=buf.getvalue())
        keys.append(key)
    return sorted(keys)


def capture_user_activity(snapshot: Path, out: Path, ns: str) -> dict:
    """Run the real analytics job for the run date, seed the 33 prior days, then run
    the real user_activity_daily.py over both.

    This is the dependent unit, so the capture reproduces the dependency rather than
    standing in for it: day 0 of both windows is whatever `analytics_daily.py` actually
    wrote a moment ago -- its `top_users.jsonl.gz` object and its Postgres row -- and
    days 1..34 are the pinned history. A capture that seeded day 0 too would be
    reconciling the target against a fixture rather than against the upstream job.

    Unlike the analytics probe, Postgres has to be reachable here: user_activity_daily.py
    exits 1 on a failed query (:117) instead of swallowing it.
    """
    s3 = aws("s3")
    history = json.loads((snapshot / "user_activity_history.json").read_text())
    days = history["days"]
    ds = legacy_analytics_date()
    day0 = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # The legacy's two windows are different widths: 31 dates of summary rows
    # (BETWEEN ds - 30 days AND ds) against 30 dates of objects (range(30)).
    summary_window = [(day0 - timedelta(days=30)).strftime("%Y-%m-%d"), ds]
    object_window = {(day0 - timedelta(days=n)).strftime("%Y-%m-%d") for n in range(30)}

    # Day 0 of both windows: the upstream job's own output, not a fixture of it.
    upstream = capture_analytics_daily(snapshot, out, ns, "p3-user-activity.upstream.json")
    if upstream["exit_code"] != 0:
        raise SystemExit(
            f"analytics_daily.py exited {upstream['exit_code']}, so the run date has no "
            f"upstream output and the dependent job would be reconciled against a "
            f"29-day window pretending to be a 30-day one.")
    if upstream["postgres_error_swallowed"]:
        raise SystemExit(
            "analytics_daily.py could not write its Postgres row (it swallows that "
            "failure, C-2.16), so the run date is missing from the summary window that "
            "user_activity_daily.py is about to read.")

    history_keys = seed_top_user_history(s3, days)
    conn = pg_connect()
    try:
        pg = seed_summary_history(conn, days, summary_window)
    finally:
        conn.close()

    expected_window_dates = sorted({d["summary"]["report_date"] for d in days
                                    if summary_window[0] <= d["summary"]["report_date"]
                                    <= summary_window[1]} | {ds})
    foreign = sorted(set(pg["dates_in_window"]) - set(expected_window_dates))
    if foreign:
        raise SystemExit(
            f"analytics_daily_summary holds {len(foreign)} row(s) inside the report "
            f"window that this capture did not seed, e.g. {foreign[:5]}. They would be "
            f"summed into the baseline's trends. Clear them, or capture against a "
            f"database no other run shares.")

    result = run_legacy("user_activity_daily.py")
    if legacy_analytics_date() != ds:
        raise SystemExit(
            f"the UTC date rolled from {ds} to {legacy_analytics_date()} during the "
            f"capture, so the windows the legacy read are not the windows this probe "
            f"seeded. Re-run it.")

    report_key = f"reports/user-activity/{ds}/activity_report.json"
    latest_key = "reports/user-activity/latest/activity_report.json"
    users_key = f"reports/user-activity/{ds}/user_summaries.jsonl"

    # Only the dated report is kept decoded. latest/ is the same document written a
    # second time and user_summaries.jsonl is report["user_summaries"] one row per
    # line, so keeping all three would triple the baseline to hold one set of
    # numbers. Their digests still say exactly what the legacy wrote.
    outputs = {}
    for obj in list_bucket(s3, DATA_LAKE_BUCKET, "reports/user-activity/"):
        body = s3.get_object(Bucket=DATA_LAKE_BUCKET, Key=obj["key"])["Body"].read()
        outputs[obj["key"]] = {"bytes": len(body),
                               "sha256": hashlib.sha256(body).hexdigest()}
        if obj["key"] == report_key:
            outputs[obj["key"]]["content"] = json.loads(body)

    report = outputs.get(report_key, {}).get("content")

    # What the history says the report must contain, derived from the snapshot rather
    # than from the report, so the assertions can contradict the run.
    read_days = [d for d in days if d["date"] in object_window]
    per_user: dict[str, dict] = {}
    for day in sorted(read_days, key=lambda d: d["day_offset"]):
        for row in day["top_users"]:
            u = per_user.setdefault(row["user_id"], {"total": 0, "days": 0})
            u["total"] += row["total"]
            u["days"] += 1
    # Day 0's own users come from the upstream job, so the expectation is a floor on
    # the distinct-user count rather than an exact figure.
    expected = {
        "summary_window": summary_window,
        "object_window_dates": sorted(object_window),
        "history_dates_in_object_window": sorted(d["date"] for d in read_days),
        "missing_day": (day0 - timedelta(days=history["missing_day_offset"])
                        ).strftime("%Y-%m-%d"),
        "reporting_days": len(expected_window_dates),
        "history_users_in_object_window": len(per_user),
        "user_summaries_cap": 500,
        "top_users_cap": 20,
    }

    result.update({
        "run_date": ds,
        "history_days_seeded": len(days),
        "history_keys": history_keys,
        "postgres": {k: v for k, v in pg.items() if k != "dates_in_window"},
        "postgres_dates_in_window": pg["dates_in_window"],
        "upstream_objects": upstream["objects_written"],
        "objects_written": sorted(outputs),
        "outputs": outputs,
        "report": report,
        # Byte identity rather than equality after parsing: the legacy writes the
        # same bytes to both keys, so a serialisation difference is a difference.
        "latest_matches_dated": (
            latest_key in outputs and report_key in outputs
            and outputs[latest_key]["sha256"] == outputs[report_key]["sha256"]),
        "wrote_user_summaries_jsonl": users_key in outputs,
        "expected": expected,
    })
    (out / "p3-user-activity.baseline.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


# ── usage rollup (Scala) ───────────────────────────────────────


def capture_usage_rollup(snapshot: Path, out: Path) -> dict:
    """Run the legacy Scala UsageRollupJob over the snapshot's NDJSON and keep its report.

    The JVM does the arithmetic, not this script. Reimplementing the aggregator in
    Python here would make the baseline agree with a converted job for whatever reason
    the reimplementation got wrong.

    The estate runs this job with its output on an emptyDir that the pod discards on
    exit (F-0.6), so there is no downstream artefact to read. The capture points
    ROLLUP_OUTPUT at a file it owns and reads the report the job wrote before exiting.

    sbt fetches its launcher from Maven Central, which rate-limits these hosts. Pass an
    already-downloaded launcher in P3_SBT_LAUNCH to skip the fetch.
    """
    service = REPO / "services" / "analytics-service"
    report = out / "usage_rollup_legacy.json"
    launcher = os.environ.get("P3_SBT_LAUNCH")
    if launcher:
        cmd = ["java", "-jar", launcher, "runMain com.otterworks.analytics.batch.UsageRollupJob"]
    elif shutil.which("sbt"):
        cmd = ["sbt", "runMain com.otterworks.analytics.batch.UsageRollupJob"]
    else:
        raise SystemExit(
            "no sbt on PATH and P3_SBT_LAUNCH is unset, so the legacy Scala job cannot "
            "be run. Record the usage baseline as unverified rather than substituting a "
            "Python reimplementation of the aggregator.")

    started = datetime.now(tz=timezone.utc)
    proc = subprocess.run(
        cmd, cwd=str(service), capture_output=True, text=True, timeout=1800, check=False,
        env={**os.environ, "TZ": "UTC", "LC_ALL": "C", "LANG": "C",
             "ROLLUP_INPUT": str(snapshot / "usage-events.ndjson"),
             "ROLLUP_OUTPUT": str(report)})
    result = {
        "job": "UsageRollupJob.scala",
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "started_at": started.isoformat(),
        "duration_s": round((datetime.now(tz=timezone.utc) - started).total_seconds(), 3),
        "input": str(snapshot / "usage-events.ndjson"),
        "report": json.loads(report.read_text()) if report.exists() else None,
    }
    report.unlink(missing_ok=True)
    (out / "p3-usage-rollup.baseline.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def legacy_analytics_date() -> str:
    """The partition date analytics_daily.py will compute for a run started now."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def legacy_audit_cutoff() -> str:
    """The cutoff audit_archive_weekly.py will compute for a run started now."""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    # Naive on purpose: the legacy builds this string the same way, and the
    # comparison is against its literal, not against a point in time.
    return (datetime.strptime(today, "%Y-%m-%d")  # noqa: DTZ007
            - timedelta(days=90)).isoformat() + "Z"


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
    ap.add_argument("--only", choices=["analytics-daily", "storage-cleanup", "audit-archive",
                                      "usage-rollup", "user-activity"],
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

    verify_snapshot(snapshot, manifest)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Observations are written to a staging directory and only promoted over
    # the committed evidence once every selected probe matched its contract.
    # A contradictory run must not become the thing the target reconciles to.
    staging = Path(tempfile.mkdtemp(prefix="p3-baseline-"))

    wanted = set(args.only or ["analytics-daily", "storage-cleanup", "audit-archive",
                               "usage-rollup", "user-activity"])
    if "user-activity" in wanted and manifest["run_date"] != today:
        # Its history is dated relative to the fixture's run_date while the legacy
        # windows itself from datetime.now(), so under drift the two do not overlap
        # and the report would be captured over a mostly empty window.
        print(f"user-activity needs the fixture's run_date ({manifest['run_date']}) to be "
              f"today ({today}): the 30-day history is dated from the fixture and the "
              f"legacy windows from datetime.now(). Regenerate with --run-date {today}.",
              file=sys.stderr)
        return 2
    summary: dict = {"kind": "p3-baseline-summary", "ns": args.ns,
                     "snapshot": str(snapshot), "captured": sorted(wanted),
                     "fixture_run_date": manifest["run_date"], "captured_on": today,
                     "audit_cutoff": manifest.get("audit_cutoff")}
    failures: list[str] = []

    def check(ok: bool, detail: str) -> None:
        if not ok:
            failures.append(detail)

    with capture_lock(), fixture_config():
        run_probes(snapshot, staging, args.ns, wanted, summary, check)

    summary["assertions_failed"] = failures
    summary["valid"] = not failures

    # A --only run replaces the probes it ran and leaves the rest of the committed
    # summary alone. Writing a fresh summary would delete the other units' evidence
    # from the file while their baseline JSONs stayed on disk, which reads as "those
    # probes were never captured".
    committed = out / "summary.json"
    if committed.exists():
        previous = json.loads(committed.read_text())
        captured_on = {**previous.get("captured_on_by_probe", {}),
                       **{probe: today for probe in sorted(wanted)}}
        summary = {**previous, **summary,
                   "captured": sorted(set(previous.get("captured", [])) | wanted),
                   "captured_on_by_probe": captured_on,
                   "assertions_failed": failures}
    (staging / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")

    if failures:
        rejected = out / "rejected" / datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rejected.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(rejected))
        print(f"\nbaseline REJECTED -- the legacy did not behave as the contract says it does.\n"
              f"The committed evidence under {out} is unchanged; this run is in {rejected}.",
              file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    for path in sorted(staging.iterdir()):
        shutil.move(str(path), str(out / path.name))
    shutil.rmtree(staging, ignore_errors=True)
    return 0


def run_probes(snapshot: Path, out: Path, ns: str, wanted: set[str],
               summary: dict, check) -> None:
    """Run each selected probe and assert it against the behaviour the contract
    records. The expectations are the point of the capture: a run that exits 0
    having observed something else is a broken capture, not a new baseline.
    """
    if "analytics-daily" in wanted:
        r = capture_analytics_daily(snapshot, out, ns)
        check(r["exit_code"] == 0,
              f"analytics_daily.py exited {r['exit_code']}, expected 0")
        check(bool(r["objects_written"]),
              "analytics_daily.py wrote no S3 objects; expected the summary, "
              "hourly breakdown and report")
        check(r["summary"] is not None,
              "analytics_daily.py wrote no summary.json.gz")
        check(r["queue_remaining"] == 0,
              f"{r['queue_remaining']} SQS messages left in the queue; F-0.1 says "
              f"the job drains it")
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
        check(not r["seeded_size_mismatches"],
              f"{len(r['seeded_size_mismatches'])} seeded objects do not have the size "
              f"the inventory declares, so every (key, size) pair here is unusable")
        check(r["exit_code"] == 0,
              f"storage_cleanup_daily.py exited {r['exit_code']}, expected 0")
        check(r["delete_set_matches_expected"],
              "the legacy's delete set is not the snapshot's orphan set as (key, size) "
              "pairs; the converted job has nothing valid to be compared against")
        summary["storage_cleanup"] = {
            "exit_code": r["exit_code"],
            "deleted": len(r["deleted_keys"]),
            "matches_expected": r["delete_set_matches_expected"],
        }
        print(f"storage_cleanup_daily.py: exit {r['exit_code']}, "
              f"deleted {len(r['deleted_keys'])}, "
              f"matches expected orphan set: {r['delete_set_matches_expected']}")

    if "audit-archive" in wanted:
        # The legacy dates its cutoff from datetime.now(), so the isolation check
        # has to use that cutoff and not the fixture's, which differ under
        # --allow-date-drift.
        p = capture_audit_archive(snapshot, out, ns, legacy_audit_cutoff())
        # F-0.4 / F-0.4a / F-0.4b. A-tsonly exiting 1 is the expected result,
        # not a failed capture: the job archives, then dies on KeyError.
        # No shape deletes from the source table.
        expected = {
            "A-estate": {"exit_code": 0, "wrote_archive": False,
                         "wrote_compliance_report": False, "rows_deleted_from_source": 0},
            "A-tsonly": {"exit_code": 1, "wrote_archive": True,
                         "rows_deleted_from_source": 0},
            "A-full": {"exit_code": 0, "wrote_archive": True,
                       "rows_deleted_from_source": 0},
        }
        check(set(p["observations"]) == set(expected),
              f"audit probes {sorted(p['observations'])} != the three contract shapes "
              f"{sorted(expected)}")
        for shape, wants in sorted(expected.items()):
            got = p["observations"].get(shape)
            if got is None:
                continue
            for field, want in sorted(wants.items()):
                check(got[field] == want,
                      f"audit_archive_weekly.py [{shape}]: {field} is {got[field]!r}, "
                      f"the contract says {want!r}")
        summary["audit_archive"] = {
            shape: {"exit_code": o["exit_code"], "wrote_archive": o["wrote_archive"],
                    "deleted": o["rows_deleted_from_source"]}
            for shape, o in p["observations"].items()
        }
        for shape, o in sorted(p["observations"].items()):
            print(f"audit_archive_weekly.py [{shape}]: exit {o['exit_code']}, "
                  f"archive written: {o['wrote_archive']}, "
                  f"source rows deleted: {o['rows_deleted_from_source']}")

    if "user-activity" in wanted:
        r = capture_user_activity(snapshot, out, ns)
        e = r["expected"]
        check(r["exit_code"] == 0,
              f"user_activity_daily.py exited {r['exit_code']}, expected 0")
        check(r["report"] is not None,
              "user_activity_daily.py wrote no dated activity_report.json")
        check(r["latest_matches_dated"],
              "the legacy writes the same document to the dated key and to latest/, and "
              "these two differ, so one of them is not the report this run produced")
        check(r["wrote_user_summaries_jsonl"],
              "no user_summaries.jsonl was written, so the optional third output is "
              "untested rather than absent by contract")
        report = r["report"] or {}
        trends = report.get("trends", {})
        check(trends.get("reporting_days") == e["reporting_days"],
              f"the report covers {trends.get('reporting_days')} summary days, the "
              f"seeded window holds {e['reporting_days']}")
        check(len(report.get("daily_summaries", [])) == e["reporting_days"],
              "daily_summaries does not carry one row per day in the summary window")
        check(e["missing_day"] in e["object_window_dates"]
              and e["missing_day"] not in e["history_dates_in_object_window"],
              f"{e['missing_day']} was supposed to be the hole in the object window "
              f"the legacy skips, and it is not")
        check(len(report.get("user_summaries", [])) == e["user_summaries_cap"],
              f"user_summaries holds {len(report.get('user_summaries', []))} rows; the "
              f"history was built to overflow the {e['user_summaries_cap']}-row cap, so "
              f"a shorter list means the cap boundary is untested")
        check(len(report.get("top_users", [])) == e["top_users_cap"],
              f"top_users holds {len(report.get('top_users', []))} rows, expected "
              f"{e['top_users_cap']}")
        summary["user_activity"] = {
            "exit_code": r["exit_code"],
            "run_date": r["run_date"],
            "reporting_days": trends.get("reporting_days"),
            "user_summaries": len(report.get("user_summaries", [])),
            "objects_written": r["objects_written"],
        }
        print(f"user_activity_daily.py: exit {r['exit_code']}, "
              f"{trends.get('reporting_days')} summary days, "
              f"{len(report.get('user_summaries', []))} user summaries, "
              f"{len(r['objects_written'])} report objects")

    if "usage-rollup" in wanted:
        manifest = json.loads((snapshot / "manifest.json").read_text())
        r = capture_usage_rollup(snapshot, out)
        check(r["exit_code"] == 0,
              f"UsageRollupJob.scala exited {r['exit_code']}, expected 0")
        report = r["report"] or {}
        seeded = manifest.get("counts", {}).get("usage_events")
        check(bool(report.get("rollups")),
              "UsageRollupJob.scala wrote no rollups; there is nothing to reconcile against")
        check(report.get("totalEvents") == seeded,
              f"the rollups account for {report.get('totalEvents')} events but the "
              f"snapshot seeded {seeded}; the JVM did not read the whole file")
        summary["usage_rollup"] = {
            "exit_code": r["exit_code"],
            "day_count": report.get("dayCount"),
            "total_events": report.get("totalEvents"),
            "window": [report.get("windowStart"), report.get("windowEnd")],
        }
        print(f"UsageRollupJob.scala: exit {r['exit_code']}, "
              f"{report.get('dayCount')} daily rollups over "
              f"{report.get('totalEvents')} events")


if __name__ == "__main__":
    raise SystemExit(main())
