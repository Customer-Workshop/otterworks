"""Byte-exact rebuild of the four files analytics_daily.py wrote to the data lake.

    python3 databricks/migration/p3/exports/analytics_report_objects.py --self-test

The Delta tables are the governed output of p3-analytics-daily. These four objects are the
external interface on top of them, and they are compared as bytes, not as rows, because
that is what a consumer reading them off S3 sees:

  analytics/daily/year=Y/month=M/day=D/summary.json.gz        json.dumps(indent=2), gzip mtime=0
  analytics/daily/year=Y/month=M/day=D/hourly_breakdown.json.gz   same
  analytics/daily/year=Y/month=M/day=D/top_users.jsonl.gz     one compact json object per line
  reports/analytics/daily/<ds>/report.json                    json.dumps(indent=2), plain

Key order is part of the bytes. The legacy builds its dicts in Python and never sorts the
inner ones, so:

  * `summary` is written in the legacy's literal key order, not alphabetically;
  * `hourly_breakdown` has its hours sorted (`dict(sorted(...))`) but the event types inside
    an hour are in first-appearance order over the frame;
  * each top_users record's `actions` map is in first-appearance order for that user.

"first appearance" is the legacy's concatenation order, which landing recorded as
`ingest_ordinal`; the ordering queries in export_analytics_reports.py read it from silver
and this module only serializes what it is handed.

`--self-test` rebuilds all four objects out of the frozen legacy bytes in
`exports/legacy_objects/p3-analytics-daily.json` and compares the digests against those
bytes. It needs no workspace and no warehouse: it is the proof that the serialization,
not just the numbers, matches.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path

LEGACY_OBJECTS = Path(__file__).resolve().parent / "legacy_objects" \
    / "p3-analytics-daily.json"

# analytics_daily.py's own key order for the summary dict it writes and embeds.
SUMMARY_KEYS = ("active_users", "active_documents", "active_files", "total_events",
                "documents_created", "documents_edited", "comments_added",
                "files_uploaded", "files_shared", "files_deleted", "bytes_uploaded")


def object_keys(ds: str) -> dict[str, str]:
    """The S3 keys the legacy wrote for run date `ds`, unchanged."""
    partition = f"analytics/daily/year={ds[:4]}/month={ds[5:7]}/day={ds[8:10]}"
    return {
        "summary": f"{partition}/summary.json.gz",
        "hourly": f"{partition}/hourly_breakdown.json.gz",
        "top_users": f"{partition}/top_users.jsonl.gz",
        "report": f"reports/analytics/daily/{ds}/report.json",
    }


def gzip_json(obj) -> bytes:
    return gzip.compress(json.dumps(obj, indent=2).encode("utf-8"), mtime=0)


def gzip_jsonl(records: list[dict]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for record in records:
            gz.write(json.dumps(record).encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


def plain_json(obj) -> bytes:
    return json.dumps(obj, indent=2).encode("utf-8")


def peak_hour(hourly: dict[str, dict[str, int]]) -> dict | None:
    """The legacy's `max(...)` over the hour dict: first hour wins a tie, and the hours are
    already sorted when it runs, so the tie goes to the earlier hour."""
    if not hourly:
        return None
    hour, counts = max(hourly.items(), key=lambda item: sum(item[1].values()))
    return {"hour": hour, "event_count": sum(counts.values())}


def report_object(ds: str, generated_at: str, summary: dict,
                  hourly: dict[str, dict[str, int]], top_users: list[dict]) -> dict:
    return {
        "report_type": "daily_analytics",
        "report_date": ds,
        "generated_at": generated_at,
        "summary": summary,
        "highlights": {
            "peak_hour": peak_hour(hourly),
            "most_active_users": [u["user_id"] for u in top_users[:5]],
        },
        "document_metrics": {
            "created": summary["documents_created"],
            "edited": summary["documents_edited"],
            "comments": summary["comments_added"],
        },
        "file_metrics": {
            "uploaded": summary["files_uploaded"],
            "shared": summary["files_shared"],
            "deleted": summary["files_deleted"],
            "bytes_uploaded": summary["bytes_uploaded"],
        },
    }


def build(ds: str, generated_at: str, summary: dict,
          hourly: dict[str, dict[str, int]], top_users: list[dict]) -> dict[str, bytes]:
    """The four objects as bytes, keyed by the S3 key the legacy used."""
    keys = object_keys(ds)
    report = report_object(ds, generated_at, summary, hourly, top_users)
    return {
        keys["summary"]: gzip_json(summary),
        keys["hourly"]: gzip_json(hourly),
        keys["top_users"]: gzip_jsonl(top_users),
        keys["report"]: plain_json(report),
    }


def decode_legacy(objects: dict) -> dict[str, bytes]:
    return {key: base64.b64decode(value["raw_b64"]) for key, value in objects.items()}


def parse_legacy(raw: dict[str, bytes]) -> dict:
    """The legacy objects as Python, with key order preserved -- that order is the point."""
    out = {}
    for key, body in raw.items():
        text = (gzip.decompress(body) if key.endswith(".gz") else body).decode("utf-8")
        name = key.rsplit("/", 1)[-1]
        out[name] = ([json.loads(line) for line in text.splitlines() if line]
                     if name.endswith(".jsonl.gz") else json.loads(text))
    return out


def self_test(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text())
    raw = decode_legacy(manifest["objects"])
    parsed = parse_legacy(raw)

    legacy_report = parsed["report.json"]
    ds = legacy_report["report_date"]
    rebuilt = build(ds, legacy_report["generated_at"], parsed["summary.json.gz"],
                    parsed["hourly_breakdown.json.gz"], parsed["top_users.jsonl.gz"])

    problems, checked = [], {}
    for key, payload in rebuilt.items():
        legacy = raw.get(key)
        if legacy is None:
            problems.append(f"{key}: the legacy wrote no such object")
            continue
        digest = hashlib.sha256(payload).hexdigest()
        checked[key] = {"bytes": len(payload), "sha256": digest,
                        "matches_legacy": payload == legacy}
        if payload != legacy:
            problems.append(
                f"{key}: rebuilt {len(payload)} bytes sha256 {digest} != legacy "
                f"{len(legacy)} bytes sha256 {hashlib.sha256(legacy).hexdigest()}")
    print(json.dumps({"legacy_objects": str(manifest_path), "run_date": ds,
                      "objects": checked}, indent=2, sort_keys=True))
    if problems:
        print("\n".join(problems))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true", required=True,
                    help="rebuild the frozen legacy objects and compare bytes")
    ap.add_argument("--legacy-objects", default=str(LEGACY_OBJECTS))
    args = ap.parse_args(argv)
    return self_test(Path(args.legacy_objects))


if __name__ == "__main__":
    raise SystemExit(main())
