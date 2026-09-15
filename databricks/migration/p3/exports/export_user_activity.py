#!/usr/bin/env python3
"""Write the legacy user-activity report objects for one run date from the gold tables.

    python3 databricks/migration/p3/exports/export_user_activity.py --run-date 2026-09-15

The Delta tables stay the governed output of p3-user-activity. This task is the file
interface on top of them: the same objects user_activity_daily.py put in the data lake,
byte for byte, under `/Volumes/ow_tp/gold/exports/user-activity/` with the legacy S3 keys
kept intact, so a consumer copies the tree to a bucket and the keys land where they were.

Every number comes from gold. Two orders also come from gold, because the legacy's output
carries them and an aggregate would throw them away:

  * users are in `rank` order -- the legacy's stable sort on `total_actions` descending,
    committed by the ranking load rather than recomputed here, so the file and the table
    can never disagree about who is 17th;
  * each user's `actions_by_type` keys are in `action_ordinal` order, which is where the
    key first appeared in the 30-day scan: newest day first, and inside a day the order
    that day's own `top_users` record wrote its `actions` keys in.

A run date with no report row writes nothing and says so, rather than shipping an empty
report the legacy never wrote.

`reports/user-activity/latest/activity_report.json` is a shared pointer, and the legacy
only ever wrote it for the day it ran. This job takes a run date, so a backfill of an older
day would otherwise move the pointer backwards for every consumer reading it. The dated
object is always written; the pointer is only overwritten when the run date is not older
than the report already sitting there.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

# A Databricks python task runs this through IPython, which defines no __file__, and it
# runs with the script's own directory as the working directory -- so the fallback is the
# bare name, not a path relative to the bundle root.
sys.path.insert(0, str(Path(globals().get("__file__", "export_user_activity.py"))
                       .resolve().parent))

from user_activity_report_objects import SUMMARY_KEYS, build, object_keys

WAREHOUSE = "565cd2fd713738c4"
EXPORT_ROOT = "/Volumes/ow_tp/gold/exports/user-activity"
REPORT = "ow_tp.gold.user_activity_report"
REPORT_DAYS = "ow_tp.gold.user_activity_report_days"
USER_SUMMARY = "ow_tp.gold.user_activity_user_summary"
USER_ACTIONS = "ow_tp.gold.user_activity_user_actions"


def query(w, statement: str, **params: str) -> list[list[str]]:
    from databricks.sdk.service.sql import StatementParameterListItem

    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s",
        parameters=[StatementParameterListItem(name=k, value=v) for k, v in params.items()])
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def read_lookback(w, run_date: str) -> int | None:
    rows = query(w, f"SELECT lookback_days FROM {REPORT} "
                    "WHERE report_date = CAST(:run_date AS DATE)", run_date=run_date)
    if len(rows) > 1:
        raise SystemExit(f"{REPORT} holds {len(rows)} rows for {run_date}; it is one row "
                         "per report, so the load did not replace the date atomically.")
    return int(rows[0][0]) if rows else None


def read_daily_summaries(w, run_date: str) -> list[dict]:
    """The `daily_summaries` array, oldest day first, as the legacy's ORDER BY returns it.

    `report_date` inside a record is the *day's* date, not the report's: the legacy ships
    the rows its query returned and its column is called report_date too.
    """
    columns = ", ".join(("summary_date",) + SUMMARY_KEYS[1:])
    rows = query(w, f"SELECT {columns} FROM {REPORT_DAYS} "
                    "WHERE report_date = CAST(:run_date AS DATE) ORDER BY summary_date",
                 run_date=run_date)
    return [{key: (value if key == "report_date" else int(value))
             for key, value in zip(SUMMARY_KEYS, row)} for row in rows]


def read_users(w, run_date: str) -> list[dict]:
    users = query(w, f"SELECT rank, user_id, total_actions, active_days FROM {USER_SUMMARY} "
                     "WHERE report_date = CAST(:run_date AS DATE) ORDER BY rank",
                  run_date=run_date)
    actions = query(w, f"SELECT rank, action_type, action_count, action_ordinal "
                       f"FROM {USER_ACTIONS} WHERE report_date = CAST(:run_date AS DATE) "
                       "ORDER BY rank, action_ordinal", run_date=run_date)
    by_rank: dict[int, dict[str, int]] = {}
    for rank, action_type, count, ordinal in actions:
        if ordinal is None:
            raise SystemExit(
                f"{USER_ACTIONS} has a row for rank {rank} with no action_ordinal, so the "
                "key order of actions_by_type cannot be recovered. Re-run the load after "
                "the ordinal column is populated.")
        by_rank.setdefault(int(rank), {})[action_type] = int(count)

    records = []
    for rank, user_id, total_actions, active_days in users:
        rank = int(rank)
        actions_by_type = by_rank.get(rank, {})
        total = sum(actions_by_type.values())
        if total != int(total_actions):
            raise SystemExit(
                f"{USER_SUMMARY} says {user_id} has {total_actions} actions on {run_date} "
                f"but {USER_ACTIONS} adds up to {total}")
        records.append({"user_id": user_id, "total_actions": int(total_actions),
                        "active_days": int(active_days),
                        "actions_by_type": actions_by_type})
    return records


def upload(w, root: str, key: str, payload: bytes) -> None:
    w.files.upload(f"{root}/{key}", io.BytesIO(payload), overwrite=True)


def published_report_date(w, root: str, key: str) -> str | None:
    """`report_date` of the object the latest pointer holds now, or None if there is none.

    An unreadable or absent pointer is treated as no pointer: the export writes one.
    """
    from databricks.sdk.errors import NotFound

    try:
        body = w.files.download(f"{root}/{key}").contents.read()
    except NotFound:
        return None
    try:
        return json.loads(body)["report_date"]
    except (ValueError, KeyError, TypeError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--export-root", default=EXPORT_ROOT)
    ap.add_argument("--generated-at", default=None,
                    help="the report's wall clock; defaults to now, as the legacy's does")
    args = ap.parse_args(argv)

    from datetime import datetime, timezone

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    lookback_days = read_lookback(w, args.run_date)
    if lookback_days is None:
        json.dump({"exported": [], "run_date": args.run_date,
                   "reason": f"{REPORT} holds no row for this date; run the report load "
                             "before the export"}, sys.stdout, sort_keys=True)
        print()
        return 1

    generated_at = args.generated_at or datetime.now(tz=timezone.utc).isoformat()
    objects = build(args.run_date, generated_at, lookback_days,
                    read_daily_summaries(w, args.run_date),
                    read_users(w, args.run_date))
    root = args.export_root.rstrip("/")
    latest_key = object_keys(args.run_date)["latest"]
    published = published_report_date(w, root, latest_key)
    held_back = published is not None and published > args.run_date

    written = {}
    for key, payload in sorted(objects.items()):
        if key == latest_key and held_back:
            continue
        upload(w, root, key, payload)
        written[key] = {"bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()}
    json.dump({"run_date": args.run_date, "export_root": args.export_root,
               "generated_at": generated_at, "exported": written,
               "latest_pointer": {"report_date": published,
                                  "kept": held_back}},
              sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit -- even
    # SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
