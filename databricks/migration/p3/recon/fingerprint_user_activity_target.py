"""Content fingerprint of the p3-user-activity target tables for one report date.

Row counts plus an order-independent md5 over whole rows, so the idempotency rerun is
compared on contents rather than on counts: a rerun that rewrote a row with a different
value but the same shape would still be caught.

    python3 fingerprint_user_activity_target.py 2026-09-15 idempotency.before.json
"""
import json
import sys

from databricks.sdk import WorkspaceClient

WAREHOUSE = "565cd2fd713738c4"
RUN_DATE = sys.argv[1]
OUT = sys.argv[2]

TABLES = [
    "gold.user_activity_report",
    "gold.user_activity_report_days",
    "gold.user_activity_user_summary",
    "gold.user_activity_user_actions",
]


def run(w, sql):
    r = w.statement_execution.execute_statement(
        statement=sql, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while r.status and r.status.state and r.status.state.value in ("PENDING", "RUNNING"):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status and r.status.state and r.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{sql} -> {r.status.state.value} {r.status.error}")
    return ((r.result.data_array if r.result else []) or [[None, None]])[0]


def main() -> int:
    w = WorkspaceClient()
    out = {"report_date": RUN_DATE, "tables": {}}
    for name in TABLES:
        sql = (
            "SELECT count(*), "
            "md5(concat_ws('|', sort_array(collect_list(to_json(struct(*)))))) "
            f"FROM ow_tp.{name} WHERE report_date = DATE '{RUN_DATE}'")
        rows, digest = run(w, sql)
        out["tables"][name] = {"rows": int(rows), "md5": digest}
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
