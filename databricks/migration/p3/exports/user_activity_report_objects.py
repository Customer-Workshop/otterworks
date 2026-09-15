"""Byte-exact rebuild of the objects user_activity_daily.py wrote to the data lake.

    python3 databricks/migration/p3/exports/user_activity_report_objects.py --self-test

The Delta tables are the governed output of p3-user-activity. These objects are the
external interface on top of them, and they are compared as bytes, not as rows, because
that is what a consumer reading them off S3 sees:

  reports/user-activity/<ds>/activity_report.json    json.dumps(indent=2, default=str)
  reports/user-activity/latest/activity_report.json  the same bytes, the admin-service pointer
  reports/user-activity/<ds>/user_summaries.jsonl    one compact record per line, only when
                                                     there is at least one user

Key order is part of the bytes. The legacy builds the report dict literally, in the order
below, and never sorts anything inside it:

  * `daily_summaries` records carry the twelve columns in the order of the legacy's own
    SELECT, with the date rendered by `isoformat()`;
  * `user_summaries` is the user list sorted on `total_actions` descending with Python's
    stable sort, so equal totals keep first-appearance order, capped at 500;
  * `top_users` is the first 20 of that same list;
  * each user's `actions_by_type` is in first-appearance order over the 30-day scan --
    newest day first, and within a day the order of the keys in that day's top_users
    record.

This module only serializes what it is handed; export_user_activity.py is where the order
is recovered from the governed tables.

`--self-test` rebuilds the objects out of the frozen legacy bytes in
`exports/legacy_objects/p3-user-activity.json` and compares digests against those bytes.
It needs no workspace and no warehouse: it is the proof that the serialization, not just
the numbers, matches.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

LEGACY_OBJECTS = Path(__file__).resolve().parent / "legacy_objects" \
    / "p3-user-activity.json"

PREFIX = "reports/user-activity"

# The legacy's SELECT order for a daily_summaries record.
SUMMARY_KEYS = ("report_date", "active_users", "active_documents", "active_files",
                "total_events", "documents_created", "documents_edited", "comments_added",
                "files_uploaded", "files_shared", "files_deleted", "bytes_uploaded")

USER_SUMMARY_CAP = 500
TOP_USER_CAP = 20


def object_keys(ds: str) -> dict[str, str]:
    """The S3 keys the legacy wrote for run date `ds`, unchanged."""
    return {
        "report": f"{PREFIX}/{ds}/activity_report.json",
        "latest": f"{PREFIX}/latest/activity_report.json",
        "user_summaries": f"{PREFIX}/{ds}/user_summaries.jsonl",
    }


def trends(daily_summaries: list[dict]) -> dict:
    total_events = sum(d.get("total_events", 0) for d in daily_summaries)
    peak_active_users = max((d.get("active_users", 0) for d in daily_summaries), default=0)
    avg = total_events / len(daily_summaries) if daily_summaries else 0
    return {
        "total_events": total_events,
        "peak_active_users": peak_active_users,
        "avg_daily_events": round(avg, 2),
        "reporting_days": len(daily_summaries),
    }


def report_object(ds: str, generated_at: str, lookback_days: int,
                  daily_summaries: list[dict], users: list[dict]) -> dict:
    return {
        "report_type": "user_activity",
        "report_date": ds,
        "generated_at": generated_at,
        "lookback_days": lookback_days,
        "trends": trends(daily_summaries),
        "daily_summaries": daily_summaries,
        "user_summaries": users[:USER_SUMMARY_CAP],
        "top_users": users[:TOP_USER_CAP],
    }


def plain_json(obj) -> bytes:
    return json.dumps(obj, indent=2, default=str).encode("utf-8")


def jsonl(records: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r, default=str) for r in records) + "\n").encode("utf-8")


def build(ds: str, generated_at: str, lookback_days: int, daily_summaries: list[dict],
          users: list[dict]) -> dict[str, bytes]:
    """The objects as bytes, keyed by the S3 key the legacy used.

    The dated report and the `latest` pointer are two puts of one `json.dumps`, so they are
    the same bytes -- including `generated_at`. `user_summaries.jsonl` is written only when
    there is a user to write, as the legacy's `if user_summaries:` does.
    """
    keys = object_keys(ds)
    report = report_object(ds, generated_at, lookback_days, daily_summaries, users)
    body = plain_json(report)
    objects = {keys["report"]: body, keys["latest"]: body}
    if report["user_summaries"]:
        objects[keys["user_summaries"]] = jsonl(report["user_summaries"])
    return objects


def decode_legacy(objects: dict) -> dict[str, bytes]:
    return {key: base64.b64decode(value["raw_b64"]) for key, value in objects.items()}


def self_test(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text())
    raw = decode_legacy(manifest["objects"])
    ds = manifest["run_date"]
    legacy_report = json.loads(raw[object_keys(ds)["report"]].decode("utf-8"))

    rebuilt = build(ds, legacy_report["generated_at"], legacy_report["lookback_days"],
                    legacy_report["daily_summaries"], legacy_report["user_summaries"])

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
    for key in sorted(set(raw) - set(rebuilt)):
        problems.append(f"{key}: the legacy wrote it and the rebuild does not")
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
