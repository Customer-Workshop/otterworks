#!/usr/bin/env python3
"""Load the captured legacy analytics output into the recon source tables.

    python3 databricks/migration/p3/recon/load_legacy_baseline_analytics.py \
        [--baseline .migration/recon/p3/baselines/p3-analytics-daily.baseline.json]

This is the SOURCE side of the p3-analytics-daily recon: the three S3 objects
`analytics_daily.py` actually wrote for the pinned fixture day, as captured by
scripts/tp_seed/capture_p3_baseline.py. The TARGET side is ow_tp.gold.analytics_daily_*,
recomputed by the converted job from the same immutable input snapshot.

Only reshaping happens here, and only where the legacy's file shape has no table shape:

* `summary.json.gz` is one JSON object -> one row.
* `top_users.jsonl.gz` is an ordered JSONL file -> one row per line, `rank` being the line
  number, plus one row per entry of that line's `actions` map. Both halves of the record
  are output, so both are compared.
* `hourly_breakdown.json.gz` nests event type inside hour -> one row per (hour, event
  type). Hour totals alone would compare green while the split inside an hour differed.

The event-type keys are loaded verbatim, including the literal `NaN` that json.dumps writes
for a row whose event type the legacy's frame could not name. It is the key the legacy
shipped, so the target reproduces it rather than the loader erasing it.

The tables are replaced on every run: they are derived evidence, and a half-refreshed
baseline is worse than none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BASELINE = ROOT / ".migration/recon/p3/baselines/p3-analytics-daily.baseline.json"

SUMMARY_TABLE = "ow_tp.bronze.p3_analytics_legacy_baseline"
TOP_USERS_TABLE = "ow_tp.bronze.p3_analytics_legacy_top_users"
HOURLY_TABLE = "ow_tp.bronze.p3_analytics_legacy_hourly"
TOP_USER_ACTIONS_TABLE = "ow_tp.bronze.p3_analytics_legacy_top_user_actions"

COUNTERS = ["total_events", "active_users", "documents_created", "documents_edited",
            "comments_added", "files_uploaded", "files_shared", "files_deleted",
            "bytes_uploaded", "active_documents", "active_files"]


def execute(w: WorkspaceClient, statement: str, params: list | None = None):
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, parameters=params or None,
        wait_timeout="50s")
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def param(name: str, value, sql_type: str) -> StatementParameterListItem:
    return StatementParameterListItem(name=name, type=sql_type,
                                      value=None if value is None else str(value))


def outputs(baseline: dict) -> dict[str, dict]:
    """The three objects, keyed by their file name, with the run date they were written for."""
    found: dict[str, dict] = {}
    for key, value in baseline["outputs"].items():
        name = key.rsplit("/", 1)[-1]
        if name in ("summary.json.gz", "top_users.jsonl.gz", "hourly_breakdown.json.gz"):
            found[name] = value
    missing = {"summary.json.gz", "top_users.jsonl.gz", "hourly_breakdown.json.gz"} - set(found)
    if missing:
        raise SystemExit(f"baseline has no {sorted(missing)}; re-capture it before reconciling")
    return found


def summary_date(baseline: dict) -> str:
    for key in baseline["outputs"]:
        if key.endswith("summary.json.gz"):
            parts = dict(p.split("=", 1) for p in key.split("/") if "=" in p)
            return f"{parts['year']}-{parts['month']}-{parts['day']}"
    raise SystemExit("baseline has no partitioned summary object to date the rows from")


def insert_rows(w: WorkspaceClient, table: str, ds: str,
                columns: list[tuple[str, str]], rows: list[tuple]) -> None:
    """Insert rows of `columns`, each row prefixed with the run date, in chunks."""
    for start in range(0, len(rows), 50):
        tuples, params = [], [param("summary_date", ds, "STRING")]
        for i, row in enumerate(rows[start:start + 50], start=start):
            markers = []
            for (name, sql_type), value in zip(columns, row):
                markers.append(f":{name}_{i}")
                params.append(param(f"{name}_{i}", value, sql_type))
            tuples.append("(CAST(:summary_date AS DATE), " + ", ".join(markers) + ")")
        execute(w, f"INSERT INTO {table} VALUES " + ", ".join(tuples), params)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    if baseline.get("exit_code") != 0:
        raise SystemExit(f"{args.baseline} records exit {baseline.get('exit_code')}; "
                         "a failed legacy run is not a recon baseline")
    files = outputs(baseline)
    ds = summary_date(baseline)

    w = WorkspaceClient()

    columns = ", ".join(f"{c} BIGINT" for c in COUNTERS)
    execute(w, f"CREATE OR REPLACE TABLE {SUMMARY_TABLE} (summary_date DATE, {columns})")
    summary = files["summary.json.gz"]["content"]
    markers = ", ".join(f":{c}" for c in COUNTERS)
    execute(w, f"INSERT INTO {SUMMARY_TABLE} VALUES (CAST(:summary_date AS DATE), {markers})",
            [param("summary_date", ds, "STRING")]
            + [param(c, summary[c], "BIGINT") for c in COUNTERS])

    execute(w, f"CREATE OR REPLACE TABLE {TOP_USERS_TABLE} "
               "(summary_date DATE, rank INT, user_id STRING, event_count BIGINT)")
    users = files["top_users.jsonl.gz"]["content"]
    for start in range(0, len(users), 50):
        chunk = users[start:start + 50]
        tuples, params = [], [param("summary_date", ds, "STRING")]
        for i, user in enumerate(chunk, start=start):
            tuples.append(f"(CAST(:summary_date AS DATE), :rank_{i}, :user_{i}, :total_{i})")
            params += [param(f"rank_{i}", i + 1, "INT"),
                       param(f"user_{i}", user["user_id"], "STRING"),
                       param(f"total_{i}", user["total"], "BIGINT")]
        execute(w, f"INSERT INTO {TOP_USERS_TABLE} VALUES " + ", ".join(tuples), params)

    execute(w, f"CREATE OR REPLACE TABLE {TOP_USER_ACTIONS_TABLE} "
               "(summary_date DATE, rank INT, user_id STRING, event_type STRING, "
               "event_count BIGINT)")
    actions = [(i + 1, user["user_id"], etype, count)
               for i, user in enumerate(users)
               for etype, count in sorted(user["actions"].items())]
    insert_rows(w, TOP_USER_ACTIONS_TABLE, ds,
                [("rank", "INT"), ("user_id", "STRING"), ("event_type", "STRING"),
                 ("event_count", "BIGINT")], actions)

    execute(w, f"CREATE OR REPLACE TABLE {HOURLY_TABLE} "
               "(summary_date DATE, hour STRING, event_type STRING, event_count BIGINT)")
    hourly = files["hourly_breakdown.json.gz"]["content"]
    hourly_rows = [(hour, etype, count)
                   for hour, per_type in sorted(hourly.items())
                   for etype, count in sorted(per_type.items())]
    insert_rows(w, HOURLY_TABLE, ds,
                [("hour", "STRING"), ("event_type", "STRING"), ("event_count", "BIGINT")],
                hourly_rows)

    print(json.dumps({"summary_date": ds,
                      SUMMARY_TABLE: 1,
                      TOP_USERS_TABLE: len(users),
                      TOP_USER_ACTIONS_TABLE: len(actions),
                      HOURLY_TABLE: len(hourly_rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
