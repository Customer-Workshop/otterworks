"""Content fingerprint of the p3-usage-rollup tables for one batch.

Row counts plus an order-independent md5 over each table's whole rows, so an idempotency
rerun is compared on contents rather than counts: a recompute that moved bytes between two
days would keep every count and move the digest.

`generated_at` and `landed_at` are excluded. They are clock readings, not output, and a
rerun is meant to change them.

    python3 fingerprint_usage_target.py p3probe idempotency.before.json
"""
import json
import sys

from databricks.sdk import WorkspaceClient

WAREHOUSE = "565cd2fd713738c4"

DIGEST = (
    "SELECT count(*), md5(concat_ws('|', sort_array(collect_list(to_json(struct({cols})))))) "
    "FROM ow_tp.{table} WHERE snapshot_batch = :batch")

RAW_COLS = ("snapshot_batch, source_line, event_id, event_type, user_id, resource_id, "
            "resource_type, event_ts, bytes_attr, metadata_json")
ROLLUP_COLS = ("snapshot_batch, date, total_events, active_users, documents_created, "
               "documents_viewed, documents_edited, files_uploaded, files_downloaded, "
               "collab_sessions, storage_allocated_bytes, storage_released_bytes, "
               "net_storage_bytes")

TABLES = (
    ("bronze.usage_events_raw", RAW_COLS),
    ("gold.usage_rollup", ROLLUP_COLS),
)


def run(w, statement: str, batch: str) -> list[str]:
    from databricks.sdk.service.sql import StatementParameterListItem

    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s",
        parameters=[StatementParameterListItem(name="batch", value=batch)])
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
    for name, cols in TABLES:
        rows, digest = run(w, DIGEST.format(table=name, cols=cols), batch)
        out["tables"][name] = {"rows": int(rows), "md5": digest}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
