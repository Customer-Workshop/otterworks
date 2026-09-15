"""Content fingerprint of the p3-audit-archive tables for one batch.

Row counts plus an order-independent md5 over each table's whole rows, so an idempotency
rerun is compared on contents: a second run that archived a different record of the same
shape would keep the count and move the digest.

`landed_at`, `archived_at` and `generated_at` are excluded. They are clock readings, not
output: including them would make every rerun differ and prove nothing.

    python3 fingerprint_audit_target.py p3probe idempotency.before.json
"""
import json
import sys

from databricks.sdk import WorkspaceClient

WAREHOUSE = "565cd2fd713738c4"

BATCH_DIGEST = (
    "SELECT count(*), md5(concat_ws('|', sort_array(collect_list(to_json(struct({cols})))))) "
    "FROM ow_tp.{table} WHERE snapshot_batch = :batch")
ALL_ROWS = ("SELECT count(*), md5(concat_ws('|', sort_array(collect_list(to_json(struct(*)))))) "
            "FROM ow_tp.{table}")

TABLES = (
    ("bronze.p3_audit_events_raw",
     "snapshot_batch, probe_shape, event_id, ts_attr, payload_json", True),
    ("bronze.p3_audit_landing_runs", "snapshot_batch, events_landed", True),
    ("silver.audit_archive",
     "snapshot_batch, run_date, probe_shape, event_id, archived_timestamp, payload_json",
     True),
    ("silver.audit_archive_run",
     ("snapshot_batch, run_date, probe_shape, retention_days, cutoff_date, events_scanned, "
      "events_archived, events_deleted_from_source, archive_location"), True),
    ("bronze.p3_audit_legacy_archive", None, False),
    ("bronze.p3_audit_legacy_run", None, False),
)


def run(w, statement: str, batch: str | None) -> list[str]:
    from databricks.sdk.service.sql import StatementParameterListItem

    params = ([StatementParameterListItem(name="batch", value=batch)]
              if batch is not None else None)
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s", parameters=params)
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{statement} -> {result.status.state.value}: {result.status.error}")
    return ((result.result.data_array if result.result else []) or [[None, None]])[0]


def main(argv: list[str]) -> int:
    batch, out_path = argv[1], argv[2]
    w = WorkspaceClient()
    out: dict = {"snapshot_batch": batch, "tables": {}}
    for name, cols, scoped in TABLES:
        statement = (BATCH_DIGEST.format(table=name, cols=cols) if scoped
                     else ALL_ROWS.format(table=name))
        rows, digest = run(w, statement, batch if scoped else None)
        out["tables"][name] = {"rows": int(rows), "md5": digest}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    if (code := main(sys.argv)):
        raise SystemExit(code)
