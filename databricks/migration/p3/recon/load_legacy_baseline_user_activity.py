"""Load the legacy user-activity report into the recon source tables.

    python3 databricks/migration/p3/recon/load_legacy_baseline_user_activity.py \
        --batch p3probe \
        [--baseline .migration/recon/p3/baselines/p3-user-activity.baseline.json]

The source side is the report `user_activity_daily.py` itself wrote to S3 for the pinned
day, captured by scripts/tp_seed/capture_p3_baseline.py --only user-activity. The one
JSON document is split into the four tables the target writes, because a blob compares
only as bytes: a wrong `active_days` on one user inside a 380 kB document is a diff no
one can read, and the same difference as a row is a keyed mismatch.

`generated_at` is not loaded. It is a wall clock, and the only thing comparing it would
prove is that two runs happened at two different times.

Every table is replaced whole on each load; a half-refreshed baseline is worse than none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BASELINE = ROOT / ".migration/recon/p3/baselines/p3-user-activity.baseline.json"

REPORT_TABLE = "ow_tp.bronze.p3_user_activity_legacy_report"
DAYS_TABLE = "ow_tp.bronze.p3_user_activity_legacy_days"
USERS_TABLE = "ow_tp.bronze.p3_user_activity_legacy_users"
ACTIONS_TABLE = "ow_tp.bronze.p3_user_activity_legacy_user_actions"

DAY_METRICS = ["active_users", "active_documents", "active_files", "total_events",
               "documents_created", "documents_edited", "comments_added",
               "files_uploaded", "files_shared", "files_deleted", "bytes_uploaded"]


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


def insert(w: WorkspaceClient, table: str, columns: list[tuple[str, str]],
           rows: list[tuple], batch: str, chunk: int = 200) -> None:
    names = ["snapshot_batch"] + [name for name, _ in columns]
    for start in range(0, len(rows), chunk):
        tuples, params = [], []
        for i, row in enumerate(rows[start:start + chunk], start=start):
            markers = [f":b_{i}"]
            params.append(StatementParameterListItem(name=f"b_{i}", type="STRING",
                                                     value=batch))
            for (name, sql_type), value in zip(columns, row):
                markers.append(f":{name}_{i}")
                params.append(StatementParameterListItem(
                    name=f"{name}_{i}", type=sql_type,
                    value=None if value is None else str(value)))
            tuples.append("(" + ", ".join(markers) + ")")
        execute(w, f"INSERT INTO {table} ({', '.join(names)}) VALUES "
                   + ", ".join(tuples), params)


def create(w: WorkspaceClient, table: str, columns: list[tuple[str, str]],
           comment: str) -> None:
    execute(w, f"CREATE OR REPLACE TABLE {table} (snapshot_batch STRING, "
               + ", ".join(f"{name} {sql_type}" for name, sql_type in columns)
               + f") COMMENT '{comment}'")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True,
                    help="snapshot batch the legacy ran against, e.g. p3probe")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    report = baseline.get("report")
    if report is None:
        raise SystemExit(f"{args.baseline} carries no report; the legacy run wrote no "
                         "activity_report.json and there is nothing to reconcile against")
    ds = report["report_date"]
    trends = report["trends"]

    report_cols = [("report_date", "DATE"), ("lookback_days", "INT"),
                   ("total_events", "BIGINT"), ("peak_active_users", "BIGINT"),
                   ("avg_daily_events", "DOUBLE"), ("reporting_days", "BIGINT")]
    report_rows = [(ds, report["lookback_days"], trends["total_events"],
                    trends["peak_active_users"], trends["avg_daily_events"],
                    trends["reporting_days"])]

    day_cols = [("report_date", "DATE"), ("summary_date", "DATE")] + [
        (name, "BIGINT") for name in DAY_METRICS]
    day_rows = [tuple([ds, day["report_date"]] + [day[name] for name in DAY_METRICS])
                for day in report["daily_summaries"]]

    user_cols = [("report_date", "DATE"), ("rank", "INT"), ("user_id", "STRING"),
                 ("total_actions", "BIGINT"), ("active_days", "BIGINT")]
    action_cols = [("report_date", "DATE"), ("rank", "INT"), ("user_id", "STRING"),
                   ("action_type", "STRING"), ("action_count", "BIGINT")]
    user_rows, action_rows = [], []
    for rank, user in enumerate(report["user_summaries"], start=1):
        user_rows.append((ds, rank, user["user_id"], user["total_actions"],
                          user["active_days"]))
        for action_type, count in user["actions_by_type"].items():
            action_rows.append((ds, rank, user["user_id"], action_type, count))

    # top_users is user_summaries[:20], so it is not loaded as a fifth table. The recon
    # compares it as rank <= 20 of the same rows; loading it twice would let a target
    # that disagrees with itself pass one of the two comparisons.
    top = report["top_users"]
    if top != report["user_summaries"][:len(top)]:
        raise SystemExit("top_users is not the first rows of user_summaries in this "
                         "baseline, so the two blocks are no longer one ranking and the "
                         "target's single ranked table cannot represent both")

    w = WorkspaceClient()
    create(w, REPORT_TABLE, report_cols,
           "trends block of the activity_report.json user_activity_daily.py wrote")
    create(w, DAYS_TABLE, day_cols, "daily_summaries block of the same report")
    create(w, USERS_TABLE, user_cols,
           "user_summaries block of the same report, ranked by list position")
    create(w, ACTIONS_TABLE, action_cols,
           "actions_by_type of each user_summaries entry, one row per action type")

    insert(w, REPORT_TABLE, report_cols, report_rows, args.batch)
    insert(w, DAYS_TABLE, day_cols, day_rows, args.batch)
    insert(w, USERS_TABLE, user_cols, user_rows, args.batch)
    insert(w, ACTIONS_TABLE, action_cols, action_rows, args.batch)

    print(json.dumps({REPORT_TABLE: len(report_rows), DAYS_TABLE: len(day_rows),
                      USERS_TABLE: len(user_rows), ACTIONS_TABLE: len(action_rows),
                      "report_date": ds, "top_users": len(top)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
