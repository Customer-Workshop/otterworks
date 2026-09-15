#!/usr/bin/env python3
"""Write the legacy audit-archive objects for one run from the governed Delta tables.

    python3 databricks/migration/p3/exports/export_audit_archive.py \
        --run-date 2026-09-15 --batch p3probe

The Delta tables stay the governed output of this unit. This task is the file interface on
top of them: the same objects `audit_archive_weekly.py` put in the archive bucket, byte for
byte, under `/Volumes/ow_tp/gold/exports/audit-archive/` with the legacy S3 keys intact.

The legacy runs against a table holding one record shape at a time and each run overwrites
the previous run's key, so "the" archive object is really three different runs' objects
sharing one key. The export keeps them apart by shape -- `<shape>/<legacy key>` -- which is
also how the byte gate compares them and how it checks that the shape the legacy left empty
is empty here too.

Nothing is re-derived that the source already decided: the line order is the source scan's
order (`scan_ordinal`) and each line is the source's own serialization of the record
(`payload_raw_json`), both landed by `landing/land_audit_events.py`. A row that reaches
here without them is a failure, not a row to re-serialize: a re-serialized record agrees on
every field and still writes different bytes.

Counts are read back from `ow_tp.silver.audit_archive_run` and have to agree with the rows
being written, so a report can never describe an archive the export did not write.
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
sys.path.insert(0, str(Path(globals().get("__file__", "export_audit_archive.py"))
                       .resolve().parent))

from audit_archive_objects import RETENTION_DAYS, build

WAREHOUSE = "565cd2fd713738c4"
EXPORT_ROOT = "/Volumes/ow_tp/gold/exports/audit-archive"
ARCHIVE = "ow_tp.silver.audit_archive"
RUNS = "ow_tp.silver.audit_archive_run"
EVENTS = "ow_tp.bronze.p3_audit_events_raw"
BUCKET = "otterworks-audit-archive"


def query(w, statement: str, **params: str) -> list[list[str]]:
    from databricks.sdk.service.sql import StatementParameterListItem

    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s",
        parameters=[StatementParameterListItem(name=k, value=v)
                    for k, v in params.items()])
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{result.status.state.value}: {result.status.error}")
    return (result.result.data_array if result.result else []) or []


def read_lines(w, run_date: str, batch: str) -> dict[str, list[str]]:
    """The archived record bodies per shape, in the order the source scan returned them."""
    rows = query(w, f"""
        SELECT a.probe_shape, r.scan_ordinal, r.payload_raw_json, a.event_id
        FROM {ARCHIVE} AS a
        JOIN {EVENTS} AS r
          ON r.snapshot_batch = a.snapshot_batch
         AND r.probe_shape = a.probe_shape
         AND r.event_id = a.event_id
        WHERE a.snapshot_batch = :batch
          AND a.run_date = CAST(:run_date AS DATE)
        ORDER BY a.probe_shape, r.scan_ordinal
    """, run_date=run_date, batch=batch)

    unordered = [f"{shape}/{event_id}" for shape, ordinal, raw, event_id in rows
                 if ordinal is None or raw is None]
    if unordered:
        raise SystemExit(
            f"{len(unordered)} archived rows carry no scan position or no source "
            f"serialization, e.g. {unordered[:5]}. The archive object's bytes are the "
            "source's own bytes in the source's own order; re-land the batch with "
            "land_audit_events.py so the export columns are filled.")

    lines: dict[str, list[str]] = {}
    for shape, _ordinal, raw, _event_id in rows:
        lines.setdefault(shape, []).append(raw)
    return lines


def read_runs(w, run_date: str, batch: str) -> dict[str, dict]:
    rows = query(w, f"""
        SELECT probe_shape, cutoff_date, events_archived, events_deleted_from_source
        FROM {RUNS}
        WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE)
    """, run_date=run_date, batch=batch)
    return {shape: {"cutoff_date": cutoff, "events_archived": int(archived),
                    "events_deleted_from_source": int(deleted)}
            for shape, cutoff, archived, deleted in rows}


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
    lines = read_lines(w, args.run_date, args.batch)
    runs = read_runs(w, args.run_date, args.batch)
    if set(lines) != set(runs):
        raise SystemExit(
            f"{ARCHIVE} holds rows for {sorted(lines)} and {RUNS} reports on "
            f"{sorted(runs)}; the compliance report and the archive describe different "
            "runs. Re-run the load tasks for this batch.")

    generated_at = args.generated_at or datetime.now(tz=timezone.utc).isoformat()
    written, root = {}, args.export_root.rstrip("/")
    for shape in sorted(lines):
        run = runs[shape]
        if run["events_archived"] != len(lines[shape]):
            raise SystemExit(
                f"{shape}: {RUNS} reports {run['events_archived']} archived events and "
                f"{ARCHIVE} holds {len(lines[shape])} for {args.run_date}")
        for key, payload in sorted(build(args.run_date, generated_at, lines[shape],
                                         run["cutoff_date"], BUCKET,
                                         run["events_deleted_from_source"]).items()):
            upload(w, root, f"{shape}/{key}", payload)
            written[f"{shape}/{key}"] = {"bytes": len(payload),
                                         "sha256": hashlib.sha256(payload).hexdigest()}

    json.dump({"run_date": args.run_date, "batch": args.batch, "export_root": root,
               "generated_at": generated_at, "retention_days": RETENTION_DAYS,
               "shapes_with_no_archive": sorted(set(runs) - set(lines)),
               "exported": written}, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit -- even
    # SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
