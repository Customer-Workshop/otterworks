#!/usr/bin/env python3
"""Report the storage-cleanup delete set, and delete only if a human has enabled it.

    python3 databricks/migration/p3/cleanup/apply_storage_cleanup.py \
        --run-date 2026-09-15 --batch p3probe

P3-D03. `storage_cleanup_daily.py` copies every orphaned object to a quarantine bucket and
then deletes the original, with no dry-run flag and no record of what it removed. That is a
one-way door, so the converted unit splits the decision from the action:

* the candidate set is computed in SQL and persisted in
  `ow_tp.silver.storage_cleanup_candidates`. That always happens;
* deleting is off. It stays off until `--enable-deletes` is passed *and* the candidate set
  is exactly equal, on (key, size), to the delete set the legacy produced for the same
  snapshot. The equality test runs here, every time, rather than being asserted by whoever
  sets the flag;
* nothing in the migration turns the flag on. It exists so the eventual owner of this job
  has a reviewed path to deleting, not so this session can take it.

The report mirrors the numbers the legacy printed and wrote to the data lake (object count,
bytes, orphan percentage, GB freed, estimated monthly saving at its own $0.023/GB figure),
so the two runs can be compared on the same terms. It is printed rather than written to S3:
the data-lake bucket the legacy writes to does not exist in this estate, which is a STOP E
fact and not something this unit invents a replacement for.
"""

from __future__ import annotations

import argparse
import json
import sys

WAREHOUSE = "565cd2fd713738c4"
CANDIDATES = "ow_tp.silver.storage_cleanup_candidates"
LEGACY_DELETE_SET = "ow_tp.bronze.p3_cleanup_legacy_delete_set"
INVENTORY = "ow_tp.bronze.p3_cleanup_inventory_raw"
LANDING_RUNS = "ow_tp.bronze.p3_cleanup_landing_runs"
# The legacy's own constant, kept so the two reports are comparable. Not a price lookup.
GB_MONTH_USD = 0.023


def client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def query(w, statement: str, **params: str) -> list[list[str]]:
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


def report(w, run_date: str, batch: str) -> dict:
    """The legacy's report numbers, recomputed from the landed listing and the candidates."""
    listed = query(
        w,
        f"SELECT count(*), coalesce(sum(size_bytes), 0) FROM {INVENTORY} "
        "WHERE snapshot_batch = :batch AND startswith(object_key, 'files/')",
        batch=batch)
    orphans = query(
        w,
        f"SELECT count(*), coalesce(sum(size_bytes), 0) FROM {CANDIDATES} "
        "WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE)",
        batch=batch, run_date=run_date)
    total_objects, total_bytes = int(listed[0][0]), int(listed[0][1])
    orphan_objects, orphan_bytes = int(orphans[0][0]), int(orphans[0][1])
    landed = query(w, f"SELECT count(*) FROM {LANDING_RUNS} WHERE snapshot_batch = :batch",
                   batch=batch)
    if int(landed[0][0]) == 0:
        raise SystemExit(
            f"{LANDING_RUNS} has no receipt for batch {batch}: the listing never landed. "
            "An unlanded listing makes every candidate set empty, which would read as a "
            "bucket with nothing to clean up.")
    freed_gb = orphan_bytes / (1024 ** 3)
    return {
        "run_date": run_date,
        "snapshot_batch": batch,
        "total_objects": total_objects,
        "total_size_bytes": total_bytes,
        "total_size_gb": round(total_bytes / (1024 ** 3), 4),
        "orphaned_objects": orphan_objects,
        "orphaned_size_bytes": orphan_bytes,
        # C-4.6: an empty bucket reports zero, as the legacy does, not a division error.
        "orphan_percentage": round(orphan_objects / total_objects * 100, 2) if total_objects else 0,
        "gb_freed": round(freed_gb, 4),
        "estimated_monthly_savings_usd": round(freed_gb * GB_MONTH_USD, 4),
        # The legacy reports what it deleted. This job reports what it would delete.
        "objects_deleted": 0,
        "objects_quarantined": 0,
    }


def equality(w, run_date: str, batch: str) -> dict:
    """Exact set equality with the legacy delete set, on (key, size)."""
    rows = query(
        w,
        f"""
        WITH target AS (
          SELECT object_key, size_bytes FROM {CANDIDATES}
          WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE)
        ), legacy AS (
          SELECT object_key, size_bytes FROM {LEGACY_DELETE_SET}
        )
        SELECT
          (SELECT count(*) FROM target),
          (SELECT count(*) FROM legacy),
          (SELECT count(*) FROM (SELECT * FROM target EXCEPT SELECT * FROM legacy)),
          (SELECT count(*) FROM (SELECT * FROM legacy EXCEPT SELECT * FROM target))
        """,
        batch=batch, run_date=run_date)
    target_rows, legacy_rows, only_target, only_legacy = (int(v) for v in rows[0])
    return {
        "target_rows": target_rows,
        "legacy_rows": legacy_rows,
        "only_in_target": only_target,
        "only_in_legacy": only_legacy,
        # An empty legacy delete set would make two empty sets "equal" and unlock deletion
        # on no evidence at all, so it is not a pass.
        "sets_equal": legacy_rows > 0 and only_target == 0 and only_legacy == 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--enable-deletes", default="false",
                    help="'true' only when a human has turned deletion on for this job. "
                         "Deletion still requires exact set equality with the legacy "
                         "delete set; the flag alone is not sufficient.")
    args = ap.parse_args(argv)

    w = client()
    result = report(w, args.run_date, args.batch)
    result["delete_set_equality"] = equality(w, args.run_date, args.batch)

    enabled = args.enable_deletes.strip().lower() == "true"
    result["deletes_enabled"] = enabled
    if not enabled:
        result["action"] = "reported only; deletion is disabled (P3-D03)"
    elif not result["delete_set_equality"]["sets_equal"]:
        raise SystemExit(
            "deletion is enabled but the candidate set is not equal to the legacy delete "
            f"set: {json.dumps(result['delete_set_equality'], sort_keys=True)}. Nothing "
            "was deleted.")
    else:
        # Reached only when a human has enabled deletion and the sets match exactly. The
        # object-mutating step itself is not implemented in this unit: no migration run may
        # perform it, and writing untested delete code that only ever runs in production is
        # the worse of the two failure modes. Wiring it is the enabling owner's change.
        raise SystemExit(
            "deletion is enabled and the delete sets match, but this unit does not "
            "delete: P3-D03 ships the decision, not the mutation. Implement and review "
            "the delete step before enabling it.")

    json.dump(result, sys.stdout, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
