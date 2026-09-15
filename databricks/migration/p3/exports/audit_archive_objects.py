#!/usr/bin/env python3
"""Serialize the two audit-archive objects exactly as audit_archive_weekly.py does.

    python3 databricks/migration/p3/exports/audit_archive_objects.py --self-test

Kept apart from the exporter so the byte-level decisions can be tested offline, against
the frozen legacy bytes, without a workspace:

  archive   one `json.dumps(record)` per line, in scan order, gzipped with `mtime=0` --
            so the object is a function of its contents and a rerun produces the same
            bytes. The record bodies are the source's own serialization, landed as
            `payload_raw_json`; re-serializing a parsed record would reorder attributes.
  report    `json.dumps(report, indent=2)`, keys in the legacy's insertion order. It
            restates the legacy's own `s3://` archive location and `GLACIER` storage
            class, because this object *is* the legacy interface and a consumer parses
            those fields. The governed statement of where the archive lives is the Delta
            table `ow_tp.silver.audit_archive_run`, whose `archive_location` names Delta;
            the two disagree on purpose and the recon report says so.

The compliance block is four booleans the legacy hard-codes to `true`. The Delta report
deliberately drops them (they are claims, not measurements). The file keeps them, because
dropping a field from a file interface is not a fidelity decision a migration gets to make
silently -- and the byte gate would fail if it did.

A shape whose records lack `event_id` gets an archive and no report: the legacy uploads
first, then builds delete keys from `event["event_id"]` and dies on the KeyError before it
reaches the report (F-0.4b). `writes_report` models exactly that, from the records.
"""

from __future__ import annotations

import gzip
import io
import json

RETENTION_DAYS = 90


def archive_key(ds: str) -> str:
    return f"audit-archive/year={ds[:4]}/week={ds}/audit_events.jsonl.gz"


def report_key(ds: str) -> str:
    return f"reports/compliance/audit-archive/{ds}/report.json"


def gzip_lines(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for line in lines:
            gz.write(line.encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


def writes_report(lines: list[str]) -> bool:
    """False when the legacy would have died on KeyError('event_id') first."""
    return all("event_id" in json.loads(line) for line in lines)


def report_object(ds: str, generated_at: str, cutoff_date: str, archived: int,
                  deleted: int, bucket: str, compressed_size: int) -> dict:
    return {
        "report_type": "audit_archive_compliance",
        "execution_date": ds,
        "generated_at": generated_at,
        "retention_policy": {
            "retention_days": RETENTION_DAYS,
            "cutoff_date": cutoff_date,
        },
        "results": {
            "events_scanned": archived,
            "events_archived": archived,
            "events_deleted_from_source": deleted,
            "archive_location": f"s3://{bucket}/{archive_key(ds)}",
            "archive_storage_class": "GLACIER",
            "compressed_size_bytes": compressed_size,
        },
        "compliance": {
            "gdpr_compliant": True,
            "soc2_compliant": True,
            "data_encrypted_at_rest": True,
            "data_encrypted_in_transit": True,
        },
    }


def build(ds: str, generated_at: str, lines: list[str], cutoff_date: str,
          bucket: str, deleted: int = 0) -> dict[str, bytes]:
    """The objects one shape's run writes, keyed by the legacy's own S3 key."""
    if not lines:
        return {}
    archive = gzip_lines(lines)
    objects = {archive_key(ds): archive}
    if writes_report(lines):
        objects[report_key(ds)] = json.dumps(
            report_object(ds, generated_at, cutoff_date, len(lines), deleted, bucket,
                          len(archive)), indent=2).encode("utf-8")
    return objects


def self_test() -> int:
    """Rebuild the frozen legacy objects from their own contents and compare bytes."""
    import base64
    import hashlib
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).resolve().parent / "legacy_objects"
         / "p3-audit-archive.json").read_text())
    ds, bucket, cutoff = manifest["run_date"], manifest["bucket"], manifest["cutoff"]
    problems, checked = [], 0
    for shape, body in sorted(manifest["shapes"].items()):
        objects = {key: base64.b64decode(entry["raw_b64"])
                   for key, entry in body["objects"].items()}
        if not objects:
            continue
        lines = gzip.decompress(objects[archive_key(ds)]).decode("utf-8").splitlines()
        report = objects.get(report_key(ds))
        generated_at = (json.loads(report.decode())["generated_at"] if report
                        else "1970-01-01T00:00:00+00:00")
        rebuilt = build(ds, generated_at, lines, cutoff, bucket)
        if sorted(rebuilt) != sorted(objects):
            problems.append(f"{shape}: rebuilt {sorted(rebuilt)}, legacy wrote "
                            f"{sorted(objects)}")
            continue
        for key, payload in sorted(rebuilt.items()):
            checked += 1
            if payload != objects[key]:
                problems.append(
                    f"{shape}/{key}: rebuilt sha256 "
                    f"{hashlib.sha256(payload).hexdigest()} != legacy "
                    f"{hashlib.sha256(objects[key]).hexdigest()}")
    for problem in problems:
        print(problem)
    print(f"{checked} objects rebuilt from the frozen legacy bytes, "
          f"{len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    if ap.parse_args().self_test and (code := self_test()):
        raise SystemExit(code)
