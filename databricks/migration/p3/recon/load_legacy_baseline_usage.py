"""Load the legacy usage-rollup output into the recon source table.

    python3 databricks/migration/p3/recon/load_legacy_baseline_usage.py --batch p3probe \
        [--baseline .migration/recon/p3/baselines/p3-usage-rollup.baseline.json]

The source side is what `UsageRollupJob.scala` itself produced for the pinned seed file,
captured by scripts/tp_seed/capture_p3_baseline.py --only usage-rollup. It is the JVM's
own arithmetic, not a Python reimplementation of the aggregator: a reimplementation would
agree with the SQL for the same wrong reason.

One row per DailyUsageRollup, columns named as the Scala names the mapping spec keys on
(totalEvents, activeUsers, ...). The report envelope -- generatedAt, source, windowStart,
windowEnd, dayCount -- is not loaded: it is the run's own summary of the rows, and
comparing a wall clock proves nothing.

The table is replaced whole on every load; a half-refreshed baseline is worse than none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BASELINE = ROOT / ".migration/recon/p3/baselines/p3-usage-rollup.baseline.json"
ROLLUP_TABLE = "ow_tp.bronze.p3_usage_legacy_rollup"

FIELDS = [
    ("date", "DATE"),
    ("totalEvents", "BIGINT"),
    ("activeUsers", "BIGINT"),
    ("documentsCreated", "BIGINT"),
    ("documentsViewed", "BIGINT"),
    ("documentsEdited", "BIGINT"),
    ("filesUploaded", "BIGINT"),
    ("filesDownloaded", "BIGINT"),
    ("collabSessions", "BIGINT"),
    ("storageAllocatedBytes", "BIGINT"),
    ("storageReleasedBytes", "BIGINT"),
    ("netStorageBytes", "BIGINT"),
]


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


def rollup_rows(baseline: dict, path: str) -> list[tuple]:
    report = baseline.get("report")
    if report is None:
        raise SystemExit(f"{path} carries no report; re-capture it with "
                         "scripts/tp_seed/capture_p3_baseline.py --only usage-rollup")
    rollups = report.get("rollups")
    if rollups is None:
        raise SystemExit(f"{path} carries a report with no rollups array; the legacy run "
                         "did not produce one and there is nothing to reconcile against")
    rows = []
    for day in rollups:
        missing = [name for name, _ in FIELDS if name not in day]
        if missing:
            raise SystemExit(f"{path}: rollup {day.get('date')!r} is missing "
                             f"{', '.join(missing)}; the baseline does not carry every "
                             "mapped field and would reconcile green on a partial target")
        rows.append(tuple(day[name] for name, _ in FIELDS))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True,
                    help="snapshot batch the legacy ran against, e.g. p3probe")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    rows = rollup_rows(baseline, args.baseline)

    w = WorkspaceClient()
    execute(w, f"CREATE OR REPLACE TABLE {ROLLUP_TABLE} (snapshot_batch STRING, "
               + ", ".join(f"{name} {sql_type}" for name, sql_type in FIELDS) + ") "
               "COMMENT 'Daily rollups UsageRollupJob.scala produced for the pinned seed "
               "file, read from its report before the pod discarded it (F-0.6).'")
    names = ["snapshot_batch"] + [name for name, _ in FIELDS]
    for start in range(0, len(rows), 25):
        tuples, params = [], []
        for i, row in enumerate(rows[start:start + 25], start=start):
            markers = [f":batch_{i}"]
            params.append(StatementParameterListItem(name=f"batch_{i}", type="STRING",
                                                     value=args.batch))
            for (name, sql_type), value in zip(FIELDS, row):
                markers.append(f":{name}_{i}")
                params.append(StatementParameterListItem(
                    name=f"{name}_{i}", type=sql_type,
                    value=None if value is None else str(value)))
            tuples.append("(" + ", ".join(markers) + ")")
        execute(w, f"INSERT INTO {ROLLUP_TABLE} ({', '.join(names)}) VALUES "
                   + ", ".join(tuples), params)

    print(json.dumps({ROLLUP_TABLE: len(rows),
                      "days": [row[0] for row in rows]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
