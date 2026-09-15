#!/usr/bin/env python3
"""Write the four legacy analytics report objects for one day from the gold tables.

    python3 databricks/migration/p3/exports/export_analytics_reports.py \
        --run-date 2026-09-15 --batch p3probe

The Delta tables stay the governed output of this unit. This task is the file interface on
top of them: the same four objects analytics_daily.py put in the data lake, byte for byte,
under `/Volumes/ow_tp/gold/exports/analytics/` with the legacy S3 keys kept intact, so a
consumer copies the tree to a bucket and the keys land where they always were.

Every number comes from gold. Only the *order* of the keys inside `hourly_breakdown` and
inside each top_users `actions` map comes from silver, because the legacy's order is the
order the events arrived in and gold aggregates that away; `ingest_ordinal` is the
concatenation order landing recorded. Gold and silver are cross-checked against each other
before anything is written: a key in one and not the other is a failure, not a missing
line in a file.

A day with no events writes nothing and succeeds -- the legacy exits 0 before it aggregates
or writes anything at all (C-2.4) -- and the absence is reported, not silent.
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
sys.path.insert(0, str(Path(globals().get("__file__", "export_analytics_reports.py"))
                       .resolve().parent))

from analytics_report_objects import SUMMARY_KEYS, build

WAREHOUSE = "565cd2fd713738c4"
EXPORT_ROOT = "/Volumes/ow_tp/gold/exports/analytics"
SUMMARY = "ow_tp.gold.analytics_daily_summary"
HOURLY = "ow_tp.gold.analytics_daily_hourly"
TOP_USERS = "ow_tp.gold.analytics_daily_top_users"
TOP_USER_ACTIONS = "ow_tp.gold.analytics_daily_top_user_actions"
SILVER = "ow_tp.silver.analytics_events_daily"


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


def read_summary(w, run_date: str, batch: str) -> dict | None:
    rows = query(w, f"SELECT {', '.join(SUMMARY_KEYS)} FROM {SUMMARY} "
                    "WHERE summary_date = CAST(:run_date AS DATE)", run_date=run_date)
    if len(rows) > 1:
        raise SystemExit(f"{SUMMARY} holds {len(rows)} rows for {run_date}; it is one row "
                         "per day, so the gold load did not replace the date atomically.")
    if not rows:
        landed = query(w, f"SELECT count(*) FROM {SILVER} WHERE summary_date = "
                          "CAST(:run_date AS DATE) AND snapshot_batch = :batch",
                       run_date=run_date, batch=batch)
        if int(landed[0][0]) > 0:
            raise SystemExit(
                f"{SUMMARY} holds no row for {run_date} while silver holds "
                f"{landed[0][0]} events for batch {batch}. Run the gold load first.")
        return None
    return {key: int(value) for key, value in zip(SUMMARY_KEYS, rows[0])}


def read_hourly(w, run_date: str, batch: str) -> dict[str, dict[str, int]]:
    counts = query(w, f"SELECT hour, event_type, event_count FROM {HOURLY} "
                      "WHERE summary_date = CAST(:run_date AS DATE)", run_date=run_date)
    order = query(w, "SELECT event_hour, coalesce(event_type, 'NaN'), min(ingest_ordinal) "
                     f"FROM {SILVER} WHERE summary_date = CAST(:run_date AS DATE) "
                     "AND snapshot_batch = :batch GROUP BY 1, 2",
                  run_date=run_date, batch=batch)
    first_seen = {(h, t): int(o) for h, t, o in order}
    counted = {(h, t): int(c) for h, t, c in counts}
    if set(first_seen) != set(counted):
        raise SystemExit(
            f"{HOURLY} and {SILVER} disagree on which (hour, event type) pairs exist for "
            f"{run_date}: {sorted(set(counted) ^ set(first_seen))}")
    hourly: dict[str, dict[str, int]] = {}
    for hour, event_type in sorted(counted, key=lambda k: (k[0], first_seen[k])):
        hourly.setdefault(hour, {})[event_type] = counted[(hour, event_type)]
    return dict(sorted(hourly.items()))


def read_top_users(w, run_date: str, batch: str) -> list[dict]:
    users = query(w, f"SELECT rank, user_id, event_count FROM {TOP_USERS} "
                     "WHERE summary_date = CAST(:run_date AS DATE) ORDER BY rank",
                  run_date=run_date)
    actions = query(w, f"SELECT rank, event_type, event_count FROM {TOP_USER_ACTIONS} "
                       "WHERE summary_date = CAST(:run_date AS DATE)", run_date=run_date)
    order = query(w, "SELECT resolved_user_id, coalesce(event_type, 'NaN'), "
                     f"min(ingest_ordinal) FROM {SILVER} "
                     "WHERE summary_date = CAST(:run_date AS DATE) "
                     "AND snapshot_batch = :batch GROUP BY 1, 2",
                  run_date=run_date, batch=batch)
    first_seen = {(u, t): int(o) for u, t, o in order}
    by_rank: dict[int, dict[str, int]] = {}
    for rank, event_type, count in actions:
        by_rank.setdefault(int(rank), {})[event_type] = int(count)

    records = []
    for rank, user_id, event_count in users:
        rank = int(rank)
        counted = by_rank.get(rank, {})
        missing = [t for t in counted if (user_id, t) not in first_seen]
        if missing:
            raise SystemExit(
                f"{TOP_USER_ACTIONS} has event types for {user_id} that {SILVER} does not "
                f"carry in batch {batch}: {sorted(missing)}")
        ordered = {t: counted[t] for t in sorted(counted, key=lambda t: first_seen[(user_id, t)])}
        total = sum(ordered.values())
        if total != int(event_count):
            raise SystemExit(
                f"{TOP_USERS} says {user_id} has {event_count} events on {run_date} but "
                f"{TOP_USER_ACTIONS} adds up to {total}")
        records.append({"user_id": user_id, "actions": ordered, "total": total})
    return records


def upload(w, root: str, key: str, payload: bytes) -> None:
    w.files.upload(f"{root}/{key}", io.BytesIO(payload), overwrite=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--export-root", default=EXPORT_ROOT)
    ap.add_argument("--generated-at", default=None,
                    help="the report's wall clock; defaults to now, as the legacy's does")
    args = ap.parse_args(argv)

    from datetime import datetime, timezone

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    summary = read_summary(w, args.run_date, args.batch)
    if summary is None:
        json.dump({"exported": [], "run_date": args.run_date, "batch": args.batch,
                   "reason": "no events for this date; the legacy writes no objects"},
                  sys.stdout, sort_keys=True)
        print()
        return 0

    generated_at = args.generated_at or datetime.now(tz=timezone.utc).isoformat()
    objects = build(args.run_date, generated_at, summary,
                    read_hourly(w, args.run_date, args.batch),
                    read_top_users(w, args.run_date, args.batch))
    written = {}
    for key, payload in sorted(objects.items()):
        upload(w, args.export_root.rstrip("/"), key, payload)
        written[key] = {"bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()}
    json.dump({"run_date": args.run_date, "batch": args.batch,
               "export_root": args.export_root, "generated_at": generated_at,
               "exported": written}, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit -- even
    # SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
