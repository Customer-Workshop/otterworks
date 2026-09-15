"""Backfill the analytics gold tables for the 30 days before the run date.

    python3 databricks/migration/p3/fixtures/seed_upstream_history.py \
        --run-date 2026-09-15 \
        --snapshot /path/to/fixtures/p3probe

Why this exists
---------------
`user_activity_daily.py` reports over a window, not over a day: 31 days of
`analytics_daily_summary` rows and 30 days of `top_users.jsonl.gz` objects. In a migrated
estate those come from `analytics_daily` having run on each of those days. This workspace
has one day of it -- the pinned run -- so without a backfill the dependent unit would be
built and reconciled against a window that is 29/30ths empty, which proves nothing about
the parts of the legacy that only appear across days: the 500-row cap, `active_days`, the
stable tie-break, and the day the legacy silently skips.

The rows come from the same pinned fixture the legacy side is seeded from
(`scripts/tp_seed/gen_p3_fixture.py` -> `user_activity_history.json`), so both sides read
one history and a difference between them is a difference in the conversion.

This is harness scaffolding, not a job task. It is never wired into a Lakeflow job: in a
real estate the history is the upstream job's own output and nothing backfills it by hand.

Write scope
-----------
The three tables belong to `p3-analytics-daily`, which owns their DDL. This writes only
dates strictly before the run date; the run date's partition stays the upstream job's, and
the script refuses to touch it. That keeps the wave-2 write set disjoint from the wave-1
one even though the table names are shared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from databricks.sdk import WorkspaceClient

WAREHOUSE = "565cd2fd713738c4"
ROOT = Path(__file__).resolve().parents[4]
FIXTURE_MANIFEST = ROOT / ".migration/recon/p3/baselines/fixture_manifest.json"
HISTORY_FILE = "user_activity_history.json"

SUMMARY_TABLE = "ow_tp.gold.analytics_daily_summary"
TOP_USERS_TABLE = "ow_tp.gold.analytics_daily_top_users"
TOP_ACTIONS_TABLE = "ow_tp.gold.analytics_daily_top_user_actions"

SUMMARY_METRICS = ["total_events", "active_users", "documents_created", "documents_edited",
                   "comments_added", "files_uploaded", "files_shared", "files_deleted",
                   "bytes_uploaded", "active_documents", "active_files"]

# The identifiers the fixture is allowed to carry. Values are inlined rather than bound,
# so anything outside this set is rejected instead of quoted and hoped for.
SAFE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")


def execute(w: WorkspaceClient, statement: str):
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def literal(value: str) -> str:
    if not SAFE.match(value):
        raise SystemExit(f"{value!r} is not a plain identifier; the fixture is not "
                         "supposed to contain one and this script inlines values")
    return f"'{value}'"


def insert_rows(w: WorkspaceClient, table: str, columns: list[str], rows: list[str],
                chunk: int = 500) -> None:
    for start in range(0, len(rows), chunk):
        execute(w, f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
                   + ", ".join(rows[start:start + chunk]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--snapshot", required=True,
                    help="the fixture snapshot gen_p3_fixture.py wrote")
    args = ap.parse_args(argv)

    run_date = datetime.strptime(args.run_date, "%Y-%m-%d").date()  # noqa: DTZ007
    path = Path(args.snapshot) / HISTORY_FILE
    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    # The legacy side of this unit is seeded from the same file. If the two sides read
    # different fixtures the recon compares two estates and calls it a conversion.
    committed = json.loads(FIXTURE_MANIFEST.read_text())["checksums"].get(HISTORY_FILE)
    if committed != digest:
        raise SystemExit(
            f"{path} hashes {digest}, but the baseline was captured against "
            f"{committed}. Regenerate the fixture, recapture the legacy baseline, or "
            f"point --snapshot at the snapshot the baseline came from.")
    history = json.loads(body)
    days = history["days"]

    dates = sorted({day["date"] for day in days})
    if args.run_date in dates:
        raise SystemExit(
            f"the history carries the run date {args.run_date}. That partition is written "
            f"by ow_tp_p3_analytics_daily; seeding it here would reconcile the dependent "
            f"unit against a fixture of its upstream instead of its upstream.")
    # The fixture deliberately runs past the 31-day summary window, and the legacy side
    # is seeded with those days too: they are how a target that windows too widely gets
    # caught. Seeding only the in-window days here would quietly remove that probe.
    horizon = (run_date - timedelta(days=30)).isoformat()
    if not [d for d in dates if d < horizon]:
        raise SystemExit(
            f"every history day falls on or after {horizon}, so both windows would hold "
            f"the whole fixture and a target that reads too far back would still pass. "
            f"Regenerate the fixture with days beyond the window.")

    date_list = ", ".join(f"DATE'{d}'" for d in dates)
    summary_rows, top_rows, action_rows = [], [], []
    for day in days:
        s, d = day["summary"], literal(day["date"])
        summary_rows.append("(DATE" + d + ", " + ", ".join(str(int(s[m]))
                                                           for m in SUMMARY_METRICS) + ")")
        for rank, row in enumerate(day["top_users"], start=1):
            uid = literal(row["user_id"])
            top_rows.append(f"(DATE{d}, {rank}, {uid}, {int(row['total'])})")
            # The key order of `actions` is the order the day's object was written in,
            # and the report a day later copies it into `actions_by_type`. Seeding the
            # rows without it would leave the dependent unit free to invent an order.
            for position, (action_type, count) in enumerate(row["actions"].items(), start=1):
                action_rows.append(f"(DATE{d}, {rank}, {uid}, {literal(action_type)}, "
                                   f"{int(count)}, {position})")

    w = WorkspaceClient()
    for table in (SUMMARY_TABLE, TOP_USERS_TABLE, TOP_ACTIONS_TABLE):
        execute(w, f"DELETE FROM {table} WHERE summary_date IN ({date_list})")

    insert_rows(w, SUMMARY_TABLE, ["summary_date"] + SUMMARY_METRICS, summary_rows)
    insert_rows(w, TOP_USERS_TABLE, ["summary_date", "rank", "user_id", "event_count"],
                top_rows)
    insert_rows(w, TOP_ACTIONS_TABLE,
                ["summary_date", "rank", "user_id", "event_type", "event_count",
                 "action_ordinal"],
                action_rows)

    counts = {}
    for table in (SUMMARY_TABLE, TOP_USERS_TABLE, TOP_ACTIONS_TABLE):
        rows = execute(w, f"SELECT count(*) FROM {table} WHERE summary_date IN ({date_list})")
        counts[table] = int(rows[0][0])
    print(json.dumps({"run_date": args.run_date, "days": len(dates),
                      "first_day": dates[0], "last_day": dates[-1],
                      "rows": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
