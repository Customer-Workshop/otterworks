#!/usr/bin/env python3
"""Publish one day of `gold.analytics_daily_summary` to the serving Postgres, loudly.

    python3 databricks/migration/p3/serving/publish_analytics_summary.py \
        --run-date 2026-09-15 --batch p3probe

The legacy wraps its Postgres upsert in `except Exception` and carries on to write its S3
report (C-2.16), so a day can exist as a report with no matching summary row and the run
still exits 0. P3-D02 changes that: this task fails, the job's retry policy gets a chance,
and a day that is not in the serving layer is visible as a failed run rather than as a
silently missing row.

The statement is the legacy's own upsert, keyed on `report_date`, so re-publishing the same
day overwrites it rather than duplicating it: the task is as re-runnable as the SQL that
feeds it.

The password is read by name from secret scope `ow_tp` (`analytics_postgres_password`),
never from `etl/config.ini`, never from an environment default, and it is never printed:
a failure reports the host and database, never the DSN.
"""

from __future__ import annotations

import argparse
import json
import sys

SUMMARY_TABLE = "ow_tp.gold.analytics_daily_summary"
SECRET_SCOPE = "ow_tp"
SECRET_KEY = "analytics_postgres_password"
WAREHOUSE = "565cd2fd713738c4"

# The legacy's column list and conflict target, unchanged. `updated_at` stays NOW() on the
# Postgres side, as it was, so the serving row's freshness keeps meaning what it meant.
COLUMNS = ("active_users", "active_documents", "active_files", "total_events",
           "documents_created", "documents_edited", "comments_added", "files_uploaded",
           "files_shared", "files_deleted", "bytes_uploaded")
UPSERT = """
    INSERT INTO analytics_daily_summary (
        report_date, active_users, active_documents, active_files,
        total_events, documents_created, documents_edited,
        comments_added, files_uploaded, files_shared,
        files_deleted, bytes_uploaded, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (report_date) DO UPDATE SET
        active_users = EXCLUDED.active_users,
        active_documents = EXCLUDED.active_documents,
        active_files = EXCLUDED.active_files,
        total_events = EXCLUDED.total_events,
        documents_created = EXCLUDED.documents_created,
        documents_edited = EXCLUDED.documents_edited,
        comments_added = EXCLUDED.comments_added,
        files_uploaded = EXCLUDED.files_uploaded,
        files_shared = EXCLUDED.files_shared,
        files_deleted = EXCLUDED.files_deleted,
        bytes_uploaded = EXCLUDED.bytes_uploaded,
        updated_at = NOW();
"""


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


def read_summary(w, run_date: str, batch: str) -> list[str] | None:
    """The one gold row for this date, in the legacy's column order, or None for an empty day.

    The gold summary is one row per day: the load replaces the whole date, so the
    batch that produced it is a property of the silver rows underneath, not of this
    table, and publishing reads the date the gold load just wrote.

    No row is not automatically an error. On a day with no events at all the legacy
    prints its warning and exits 0 before it aggregates, publishes, or writes a report
    (C-2.4), so the target must also publish nothing and succeed. What distinguishes
    that from a broken run is silver: events present with no summary above them means
    the transformation did not run, and that is still a failure.
    """
    rows = query(
        w,
        f"SELECT {', '.join(COLUMNS)} FROM {SUMMARY_TABLE} "
        "WHERE summary_date = CAST(:run_date AS DATE)",
        run_date=run_date)
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise SystemExit(
            f"{SUMMARY_TABLE} holds {len(rows)} rows for {run_date}; it is one row per "
            "day, so the gold load did not replace the date atomically.")
    landed = query(
        w,
        "SELECT count(*) FROM ow_tp.silver.analytics_events_daily "
        "WHERE summary_date = CAST(:run_date AS DATE) AND snapshot_batch = :batch",
        run_date=run_date, batch=batch)
    if int(landed[0][0]) > 0:
        raise SystemExit(
            f"{SUMMARY_TABLE} holds no row for {run_date} while silver holds "
            f"{landed[0][0]} events for batch {batch}. Run the gold load for this date "
            "before publishing.")
    return None


def publish(dsn_parts: dict, password: str, run_date: str, values: list[str]) -> None:
    import psycopg2

    conn = None
    try:
        conn = psycopg2.connect(password=password, **dsn_parts)
        with conn.cursor() as cursor:
            cursor.execute(UPSERT, (run_date, *[int(v) for v in values]))
        conn.commit()
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        # Deliberately not swallowed (P3-D02). The message names the endpoint, never the
        # credential: psycopg2 errors do not carry the password, and nothing here adds it.
        raise SystemExit(
            f"publishing {run_date} to {dsn_parts['host']}:{dsn_parts['port']}/"
            f"{dsn_parts['dbname']} failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--pg-host", required=True)
    ap.add_argument("--pg-port", default="5432")
    ap.add_argument("--pg-database", required=True)
    ap.add_argument("--pg-user", required=True)
    args = ap.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    values = read_summary(w, args.run_date, args.batch)
    if values is None:
        json.dump({"published": None, "run_date": args.run_date, "batch": args.batch,
                   "reason": "no events for this date; nothing to publish"},
                  sys.stdout, sort_keys=True)
        print()
        return 0
    publish({"host": args.pg_host, "port": int(args.pg_port),
             "dbname": args.pg_database, "user": args.pg_user},
            w.dbutils.secrets.get(SECRET_SCOPE, SECRET_KEY), args.run_date, values)
    json.dump({"published": args.run_date, "batch": args.batch,
               "table": "analytics_daily_summary"}, sys.stdout, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
