"""Report the audit-archive run and assert that nothing was pruned from the source.

    python3 databricks/migration/p3/audit/apply_audit_archive.py \
        --run-date 2026-09-15 --batch p3probe

The archiving itself is the SQL in sql/audit_archive/; this is the run's report, the same
way apply_storage_cleanup.py is the cleanup run's report. It exists to say three things
out loud rather than leave them implied:

  * the scan was landed. Zero archived events is a legitimate outcome — it is what the
    legacy does against the shape the audit-service really writes (F-0.4) — so an empty
    archive cannot be treated as a failure. A scan that never landed produces the same
    empty archive for an entirely different reason, and the landing receipt is what tells
    the two apart;
  * the report is per record shape, and a shape that archived nothing gets no report row,
    because the legacy exits before writing its compliance report in that case;
  * source deletions are zero. This unit holds no DynamoDB client and issues no delete on
    any path (P3-D04); the number is printed so the compliance reader sees the claim
    rather than inferring it from the absence of code.
"""

from __future__ import annotations

import argparse
import json

WAREHOUSE = "565cd2fd713738c4"
ARCHIVE = "ow_tp.silver.audit_archive"
RUNS = "ow_tp.silver.audit_archive_run"
LANDING_RUNS = "ow_tp.bronze.p3_audit_landing_runs"
EVENTS = "ow_tp.bronze.p3_audit_events_raw"


def client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def query(w, statement: str, **params) -> list[list[str]]:
    from databricks.sdk.service.sql import StatementParameterListItem

    used = [StatementParameterListItem(name=k, value=v)
            for k, v in params.items() if f":{k}" in statement]
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, parameters=used or None,
        wait_timeout="50s")
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def require_landed(w, batch: str) -> int:
    landed = query(
        w, f"SELECT coalesce(max(events_landed), -1) FROM {LANDING_RUNS} "
           "WHERE snapshot_batch = :batch", batch=batch)
    events_landed = int(landed[0][0])
    if events_landed < 0:
        raise SystemExit(
            f"{LANDING_RUNS} has no receipt for batch {batch}: the scan never landed. "
            "An unlanded scan archives nothing, which would read as a source with no "
            "events old enough to archive.")
    return events_landed


def report(w, run_date: str, batch: str) -> dict:
    rows = query(
        w,
        f"SELECT probe_shape, retention_days, cutoff_date, events_scanned, events_archived, "
        f"events_deleted_from_source, archive_location FROM {RUNS} "
        "WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE) "
        "ORDER BY probe_shape",
        batch=batch, run_date=run_date)
    shapes = [{
        "probe_shape": r[0],
        "retention_days": int(r[1]),
        "cutoff_date": r[2],
        "events_scanned": int(r[3]),
        "events_archived": int(r[4]),
        "events_deleted_from_source": int(r[5]),
        "archive_location": r[6],
    } for r in rows]
    deleting = [s for s in shapes if s["events_deleted_from_source"] != 0]
    if deleting:
        raise SystemExit(
            "the compliance report claims source deletions on "
            f"{[s['probe_shape'] for s in deleting]}; this unit deletes nothing (P3-D04), "
            "so a non-zero count means the report was written by something else")
    archived = query(
        w, f"SELECT count(*) FROM {ARCHIVE} WHERE snapshot_batch = :batch "
           "AND run_date = CAST(:run_date AS DATE)", batch=batch, run_date=run_date)
    scanned = query(
        w, f"SELECT count(*) FROM {EVENTS} WHERE snapshot_batch = :batch", batch=batch)
    return {
        "run_date": run_date,
        "snapshot_batch": batch,
        "events_in_source": int(scanned[0][0]),
        "events_archived": int(archived[0][0]),
        "events_deleted_from_source": 0,
        "shapes": shapes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--batch", required=True)
    args = ap.parse_args(argv)

    w = client()
    landed = require_landed(w, args.batch)
    result = report(w, args.run_date, args.batch)
    result["events_landed"] = landed
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
