#!/usr/bin/env python3
"""Manually run the disabled Oracle JOB_NIGHTLY_DUNNING action.

The source job is defined with ``enabled => FALSE``.  This entrypoint activates
no schedule; it only performs one explicitly requested manual run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from tp_mongo.dunning_service import DunningService
from tp_mongo.rating_service import TARGET_DB

REPO_ROOT = Path(__file__).resolve().parents[1].parent


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri-secret",
        default="MONGODB_ATLAS_URI",
        help="environment variable name containing the Mongo URI",
    )
    parser.add_argument("--target-db", default=TARGET_DB)
    parser.add_argument(
        "--as-of",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="as-of date in YYYY-MM-DD (default: today UTC)",
    )
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U6/job_nightly_dunning.json"),
    )
    return parser.parse_args()


def _secret_value(name: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"Mongo URI environment variable name '{name}' is not set")
    return os.environ[name]


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    as_of = date.fromisoformat(args.as_of)
    uri_value = _secret_value(args.uri_secret)

    from pymongo import MongoClient

    client = MongoClient(uri_value)
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        service = DunningService(client[args.target_db])
        scheduled = service.schedule_dunning(as_of)
        suspended = service.suspend_overdue(as_of)
    finally:
        client.close()
    finished_at = datetime.now(timezone.utc).isoformat()
    report = {
        "kind": "job-run-report",
        "job": "JOB_NIGHTLY_DUNNING",
        "source_enabled": False,
        "schedule_activated": False,
        "target_db": args.target_db,
        "as_of": as_of,
        "secret_names": {"uri": args.uri_secret},
        "started_at": started_at,
        "finished_at": finished_at,
        "schedule_dunning": scheduled,
        "suspend_overdue": suspended,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(
        f"JOB_NIGHTLY_DUNNING | as_of={as_of} "
        f"scheduled={scheduled['scheduled']} suspended={len(suspended['suspended'])} "
        f"notifications_inserted={suspended['notifications_inserted']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
