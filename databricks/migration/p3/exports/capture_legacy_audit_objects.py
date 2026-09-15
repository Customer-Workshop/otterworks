#!/usr/bin/env python3
"""Freeze the audit-archive objects the legacy writes, per record shape, as bytes.

    AWS_ENDPOINT_URL=http://localhost:4566 \
    python3 databricks/migration/p3/exports/capture_legacy_audit_objects.py \
        --snapshot /path/to/fixtures/p3probe --run-date 2026-09-15

`capture_legacy_objects.py` freezes objects that are still sitting in the estate's S3.
The audit unit cannot be captured that way: the wave-0 probe runs the legacy once per
record shape against a table holding only that shape, and each run empties the bucket
first, so the estate only ever holds the last shape's archive. The bytes of the A-full
run -- the only shape that writes a compliance report -- exist nowhere. The recon
baseline recorded the *parsed* records and the parsed report, which is exactly what the
byte gate cannot be built on.

So this re-runs the same probe, in the same order, and records three things the baseline
did not:

  raw bytes      the archive object and the compliance report exactly as uploaded,
                 base64'd into the frozen manifest the compare task reads.
  scan order     the order the legacy's own scan hands the records over. The archive is
                 one JSON line per record in that order, and it is a property of the
                 table's layout, not of the snapshot file.
  attribute order  the order boto3 returns each record's attributes in, which is the key
                 order `json.dumps` then writes. It is neither the snapshot file's order
                 nor sorted, so a target that agrees on every field still writes
                 different bytes without it.

Nothing here is taken on trust: every shape's parsed records and parsed report are
checked against the committed baseline before the bytes are written, so a manifest can
only be produced from a run that reproduced the evidence the unit was reconciled against.

The re-run seeds the fixture namespace into the estate's audit table exactly as the
wave-0 capture does, under the same host lock, and deletes nothing outside it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "tp_seed"))

import capture_p3_baseline as cap

BASELINE = ROOT / ".migration/recon/p3/baselines/p3-audit-archive.baseline.json"
MANIFEST = Path(__file__).resolve().parent / "legacy_objects" / "p3-audit-archive.json"
ORDER_FILE = "audit_source_order.json"


def scan_in_order(table, cutoff: str) -> list[dict]:
    """The records the legacy's own scan returns, in the order it returns them.

    Same filter expression, same pagination. Read-only: it writes nothing back.
    """
    items, kwargs = [], {"FilterExpression": "#ts < :cutoff",
                         "ExpressionAttributeNames": {"#ts": "timestamp"},
                         "ExpressionAttributeValues": {":cutoff": cutoff}}
    while True:
        page = table.scan(**kwargs)
        items += page.get("Items", [])
        last = page.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def raw_object(s3, bucket: str, key: str) -> bytes:
    """The object's bytes, thawing it first when the legacy wrote it to Glacier."""
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except s3.exceptions.InvalidObjectState:
        s3.restore_object(Bucket=bucket, Key=key,
                          RestoreRequest={"Days": 1,
                                          "GlacierJobParameters": {"Tier": "Expedited"}})
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def identity(record: dict) -> str:
    return record.get("event_id") or record.get("id") or record.get("Id")


def seed_shape(table, ns: str, rows: list[dict]) -> None:
    """Leave the fixture namespace holding this shape and nothing else."""
    kwargs: dict = {"FilterExpression": "#n = :ns",
                    "ExpressionAttributeNames": {"#n": "ns"},
                    "ExpressionAttributeValues": {":ns": ns}}
    while True:
        page = table.scan(**kwargs)
        with table.batch_writer() as batch:
            for item in page.get("Items", []):
                batch.delete_item(Key={"id": item["id"]})
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    with table.batch_writer() as batch:
        for item in rows:
            batch.put_item(Item=item)


def parsed(body: bytes, key: str) -> list[dict] | dict:
    import gzip

    if key.endswith(".gz"):
        return [json.loads(line) for line in
                gzip.decompress(body).decode("utf-8").splitlines() if line]
    return json.loads(body.decode("utf-8"))


def check_against_baseline(shape: str, observed: dict, recorded: dict) -> list[str]:
    """The re-run has to reproduce the baseline, or its bytes describe another run."""
    problems = []
    if sorted(observed) != sorted(recorded["archive_objects_by_key"]):
        return [(f"{shape}: wrote {sorted(observed)}, the baseline recorded "
                 f"{sorted(recorded['archive_objects_by_key'])}")]
    for key, body in sorted(observed.items()):
        content = parsed(body, key)
        if key.endswith(".gz"):
            if content != recorded["archived_records"]:
                problems.append(
                    f"{shape}/{key}: the re-run archived different records than the "
                    "baseline; the manifest would freeze bytes from another run")
        else:
            want = dict(recorded["compliance_report"])
            got = dict(content)
            # generated_at is datetime.now() in the legacy and is the one field a
            # faithful re-run is expected to differ on.
            want.pop("generated_at", None)
            got.pop("generated_at", None)
            if got != want:
                problems.append(
                    f"{shape}/{key}: the re-run's compliance report differs from the "
                    "baseline by more than generated_at")
    return problems


def capture(snapshot: Path, run_date: str) -> tuple[dict, dict]:
    baseline = json.loads(BASELINE.read_text())
    ns = baseline["ns"]
    cutoff = cap.legacy_audit_cutoff()
    ds = cap.legacy_analytics_date()
    if ds != run_date:
        raise SystemExit(
            f"the legacy dates itself from the wall clock and would write {ds} objects, "
            f"not {run_date}; capturing now would freeze a different run's keys")

    slices = json.loads((snapshot / "audit_events.json").read_text())
    s3 = cap.aws("s3")
    table = cap.aws_resource("dynamodb").Table(cap.AUDIT_TABLE)
    cap.ensure_bucket(s3, cap.ARCHIVE_BUCKET)

    shapes, order, problems = {}, {}, []
    with cap.capture_lock(), cap.fixture_config():
        for shape, rows in sorted(slices.items()):
            seed_shape(table, ns, rows)
            cap.require_isolated(
                table,
                {"FilterExpression": "#ts < :cutoff",
                 "ExpressionAttributeNames": {"#ts": "timestamp"},
                 "ExpressionAttributeValues": {":cutoff": cutoff}},
                {item["id"] for item in rows},
                "capture_legacy_audit_objects.py")

            scanned = scan_in_order(table, cutoff)
            order[shape] = [{"event_id": identity(record),
                             "attribute_order": list(record)} for record in scanned]

            cap.empty_bucket(s3, cap.ARCHIVE_BUCKET)
            run = cap.run_legacy("audit_archive_weekly.py")
            bodies = {obj["key"]: raw_object(s3, cap.ARCHIVE_BUCKET, obj["key"])
                      for obj in cap.list_bucket(s3, cap.ARCHIVE_BUCKET)}

            recorded = dict(baseline["observations"][shape])
            recorded["archive_objects_by_key"] = {
                obj["key"]: obj["size"] for obj in recorded["archive_objects"]}
            if run["exit_code"] != recorded["exit_code"]:
                problems.append(f"{shape}: exit {run['exit_code']}, baseline recorded "
                                f"{recorded['exit_code']}")
            problems += check_against_baseline(shape, bodies, recorded)

            objects = {}
            for key, body in sorted(bodies.items()):
                entry = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                         "raw_b64": base64.b64encode(body).decode("ascii")}
                if key.endswith("report.json"):
                    entry["wallclock_field"] = "generated_at"
                    entry["wallclock_value"] = json.loads(body.decode())["generated_at"]
                objects[key] = entry
            shapes[shape] = {"objects": objects, "exit_code": run["exit_code"],
                             "records_scanned": len(scanned),
                             "reason": baseline["contract_expectation"][shape]}

    if problems:
        raise SystemExit("\n".join(problems))

    manifest = {
        "unit": "p3-audit-archive",
        "run_date": run_date,
        "bucket": cap.ARCHIVE_BUCKET,
        "export_root": "/Volumes/ow_tp/gold/exports/audit-archive",
        "cutoff": cutoff,
        "source": "a re-run of the wave-0 audit probe, checked against "
                  ".migration/recon/p3/baselines/p3-audit-archive.baseline.json",
        "shapes": shapes,
    }
    source_order = {"table": cap.AUDIT_TABLE, "run_date": run_date, "cutoff": cutoff,
                    "scan_filter": "#ts < :cutoff on the lowercase timestamp attribute",
                    "shapes": order}
    return manifest, source_order


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="the pinned input snapshot")
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    manifest, order = capture(Path(args.snapshot), args.run_date)
    out = Path(args.out) if args.out else MANIFEST
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (Path(args.snapshot) / ORDER_FILE).write_text(
        json.dumps(order, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(out),
                      "order_file": str(Path(args.snapshot) / ORDER_FILE),
                      "objects": {shape: sorted(body["objects"])
                                  for shape, body in manifest["shapes"].items()}},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
