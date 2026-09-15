"""Content fingerprint of the p3-analytics-daily target tables for one run date.

Writes row counts plus an order-independent md5 over each table's rows, so an
idempotency rerun is compared on contents rather than on counts alone: a reload that
replaced a row with a different one of the same shape would keep the count and move
the digest.

    python3 fingerprint_analytics_target.py 2026-09-15 idempotency.before.json
"""
import json
import sys

from databricks.sdk import WorkspaceClient

WAREHOUSE = "565cd2fd713738c4"

# Whole rows, not keys: a rerun that kept every identifier and changed a payload, an
# attribution or a size would keep the count and the key digest and still be a different
# table, which is exactly the failure this evidence exists to catch.
ALL_ROWS = ("SELECT count(*), md5(concat_ws('|', sort_array(collect_list(to_json(struct(*)))))) "
            "FROM {table}")
ROW_DIGEST = ALL_ROWS + " WHERE summary_date = CAST(:run_date AS DATE)"

TABLES = (
    ("bronze.analytics_events_raw", ALL_ROWS, False),
    ("silver.analytics_events_daily", ALL_ROWS, False),
    ("gold.analytics_daily_summary", ROW_DIGEST, True),
    ("gold.analytics_daily_top_users", ROW_DIGEST, True),
    ("gold.analytics_daily_hourly", ROW_DIGEST, True),
    ("gold.analytics_daily_top_user_actions", ROW_DIGEST, True),
)


def run(w, statement: str, run_date: str | None) -> list[str]:
    from databricks.sdk.service.sql import StatementParameterListItem

    params = ([StatementParameterListItem(name="run_date", value=run_date)]
              if run_date is not None else None)
    result = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=WAREHOUSE, wait_timeout="50s", parameters=params)
    while result.status and result.status.state and result.status.state.value in (
            "PENDING", "RUNNING"):
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status and result.status.state and result.status.state.value != "SUCCEEDED":
        raise SystemExit(f"{statement} -> {result.status.state.value}: {result.status.error}")
    return ((result.result.data_array if result.result else []) or [[None, None]])[0]


def main(argv: list[str]) -> int:
    run_date, out_path = argv[1], argv[2]
    w = WorkspaceClient()
    out: dict = {"run_date": run_date, "tables": {}}
    for name, template, dated in TABLES:
        rows, digest = run(w, template.format(table=f"ow_tp.{name}"),
                           run_date if dated else None)
        out["tables"][name] = {"rows": int(rows), "md5": digest}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    if (code := main(sys.argv)):
        raise SystemExit(code)
