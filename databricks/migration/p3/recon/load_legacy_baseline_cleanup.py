#!/usr/bin/env python3
"""Load the legacy storage-cleanup delete set into the recon source table.

    python3 databricks/migration/p3/recon/load_legacy_baseline_cleanup.py --batch p3probe \
        [--baseline .migration/recon/p3/baselines/p3-storage-cleanup.baseline.json]

The source side of this unit's recon is not a file the legacy wrote: it is what the legacy
*removed*. `capture_p3_baseline.py` runs `storage_cleanup_daily.py` against a per-run clone
of the pinned snapshot and derives the delete set as (snapshot contents) minus (clone
contents after the run), with the size each removed object had. That derivation is the only
honest source side here, because the legacy has no dry-run mode and its report counts
objects without naming them.

Sizes travel with the keys. The legacy copies an object to quarantine and then deletes the
original, so a copy that truncated would leave the key present and the bytes gone; a
key-only comparison would call that a successful match.

The rows carry the snapshot batch they were derived from, so the recon can scope both sides
to one run. The table is replaced on every run: it is derived evidence, and a
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
DEFAULT_BASELINE = ROOT / ".migration/recon/p3/baselines/p3-storage-cleanup.baseline.json"
DELETE_SET_TABLE = "ow_tp.bronze.p3_cleanup_legacy_delete_set"


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


def delete_set(baseline: dict, path: str) -> list[dict]:
    if baseline.get("exit_code") != 0:
        raise SystemExit(f"{path} records exit {baseline.get('exit_code')}; "
                         "a failed legacy run is not a recon baseline")
    removed = baseline.get("deleted_with_size")
    if removed is None:
        raise SystemExit(f"{path} carries no deleted_with_size; re-capture it with "
                         "scripts/tp_seed/capture_p3_baseline.py")
    if baseline.get("seeded_size_mismatches"):
        raise SystemExit(
            f"{path} reports seeded size mismatches "
            f"{baseline['seeded_size_mismatches']}; the clone drifted from the snapshot, "
            "so the derived delete set is not the legacy's")
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True,
                    help="snapshot batch the legacy ran against, e.g. p3probe")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    removed = delete_set(baseline, args.baseline)

    w = WorkspaceClient()
    execute(w, f"CREATE OR REPLACE TABLE {DELETE_SET_TABLE} "
               "(snapshot_batch STRING, object_key STRING, size_bytes BIGINT) "
               "COMMENT 'Objects storage_cleanup_daily.py removed from its isolated clone "
               "of the pinned snapshot, with the size each one had.'")
    for start in range(0, len(removed), 50):
        tuples, params = [], []
        for i, obj in enumerate(removed[start:start + 50], start=start):
            tuples.append(f"(:batch_{i}, :key_{i}, :size_{i})")
            params += [param(f"batch_{i}", args.batch, "STRING"),
                       param(f"key_{i}", obj["key"], "STRING"),
                       param(f"size_{i}", obj["size"], "BIGINT")]
        execute(w, f"INSERT INTO {DELETE_SET_TABLE} VALUES " + ", ".join(tuples), params)

    print(json.dumps({DELETE_SET_TABLE: len(removed),
                      "objects_before": baseline.get("objects_before"),
                      "objects_after": baseline.get("objects_after")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
