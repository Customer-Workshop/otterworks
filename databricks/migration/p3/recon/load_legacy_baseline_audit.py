"""Load the legacy audit-archive output into the recon source tables.

    python3 databricks/migration/p3/recon/load_legacy_baseline_audit.py --batch p3probe \
        [--baseline .migration/recon/p3/baselines/p3-audit-archive.baseline.json]

The source side is what `audit_archive_weekly.py` actually wrote, per record shape:
`capture_p3_baseline.py` runs it three times against isolated clones of the pinned
snapshot, reads back the archive object it uploaded (issuing a restore first, because the
legacy writes it as GLACIER), and records the decoded rows.

Two tables come out of that:

  p3_audit_legacy_archive  one row per archived record, with the body as canonical JSON.
  p3_audit_legacy_run      one row per shape that produced a run, with the counts.

The A-estate shape archives nothing (F-0.4), so it contributes no rows to either table,
and the recon's pass there is an empty set matching an empty set rather than a gap.

The A-tsonly shape exits 1 *after* uploading its archive, on a KeyError raised while
building delete keys. Its archived rows are still what the legacy archived, so they are
loaded and compared; the exit code is a behavioural clause in the recon report, not a row.
A non-zero exit is not a reason to drop evidence the run already committed.

Both tables are replaced whole on every load: they are derived evidence, and a
half-refreshed baseline is worse than none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BASELINE = ROOT / ".migration/recon/p3/baselines/p3-audit-archive.baseline.json"
ARCHIVE_TABLE = "ow_tp.bronze.p3_audit_legacy_archive"
RUN_TABLE = "ow_tp.bronze.p3_audit_legacy_run"


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


def archived_rows(baseline: dict, path: str) -> tuple[list[tuple], list[tuple]]:
    """(archive rows, run rows) derived from the per-shape observations."""
    observations = baseline.get("observations")
    if not observations:
        raise SystemExit(f"{path} carries no observations; re-capture it with "
                         "scripts/tp_seed/capture_p3_baseline.py")
    archive, runs = [], []
    for shape, run in sorted(observations.items()):
        records = run.get("archived_records")
        if records is None:
            raise SystemExit(
                f"{path} [{shape}] carries no archived_records, only the object listing. "
                "The recon compares the archived bodies, so re-capture the baseline.")
        if run.get("wrote_archive") and not records:
            raise SystemExit(
                f"{path} [{shape}] says an archive was written but carries no rows from "
                "it; the capture could not read the object back")
        for record in records:
            identity = record.get("event_id") or record.get("id") or record.get("Id")
            archive.append((shape, identity, record.get("timestamp"),
                            json.dumps(record, sort_keys=True, separators=(",", ":"))))
        if records:
            runs.append((shape, len(records), int(run.get("rows_deleted_from_source", 0))))
    return archive, runs


def load(w: WorkspaceClient, table: str, ddl: str, columns: list[tuple[str, str]],
         batch: str, rows: list[tuple]) -> None:
    execute(w, ddl)
    names = ["batch"] + [n for n, _ in columns]
    for start in range(0, len(rows), 25):
        tuples, params = [], []
        for i, row in enumerate(rows[start:start + 25], start=start):
            markers = [f":batch_{i}"]
            params.append(param(f"batch_{i}", batch, "STRING"))
            for (name, sql_type), value in zip(columns, row):
                markers.append(f":{name}_{i}")
                params.append(param(f"{name}_{i}", value, sql_type))
            tuples.append("(" + ", ".join(markers) + ")")
        execute(w, f"INSERT INTO {table} ({', '.join(names)}) VALUES " + ", ".join(tuples),
                params)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True,
                    help="snapshot batch the legacy ran against, e.g. p3probe")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    archive, runs = archived_rows(baseline, args.baseline)

    w = WorkspaceClient()
    load(w, ARCHIVE_TABLE,
         f"CREATE OR REPLACE TABLE {ARCHIVE_TABLE} (batch STRING, probe_shape STRING, "
         "event_id STRING, archived_timestamp STRING, payload_json STRING) "
         "COMMENT 'Records audit_archive_weekly.py archived to S3, read back per shape.'",
         [("probe_shape", "STRING"), ("event_id", "STRING"),
          ("archived_timestamp", "STRING"), ("payload_json", "STRING")],
         args.batch, archive)
    load(w, RUN_TABLE,
         f"CREATE OR REPLACE TABLE {RUN_TABLE} (batch STRING, probe_shape STRING, "
         "events_archived BIGINT, events_deleted_from_source BIGINT) "
         "COMMENT 'Per-shape legacy run counts. Deletions are zero on every shape: the "
         "delete keys do not match the table schema and the error is swallowed.'",
         [("probe_shape", "STRING"), ("events_archived", "BIGINT"),
          ("events_deleted_from_source", "BIGINT")],
         args.batch, runs)

    print(json.dumps({ARCHIVE_TABLE: len(archive), RUN_TABLE: len(runs),
                      "shapes": sorted(baseline["observations"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
