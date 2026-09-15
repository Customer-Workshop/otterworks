#!/usr/bin/env python3
"""Run a pipeline-3 SQL file on the migration warehouse, with named parameters.

    python3 databricks/migration/p3/sql/apply_p3_sql.py analytics_daily/21_load_gold_*.sql \
        --param run_date=2026-09-15 --param batch=p3probe

One statement per file, so the same text runs here, runs from the Lakeflow job task, and
diffs cleanly between the two. Parameters are bound as SQL parameter markers (`:run_date`),
never substituted into the text.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
# A Databricks python task execs this file, so there is no __file__ to resolve
# against; it passes the paths relative to the bundle root instead.
SQL_DIR = Path(globals().get("__file__", "sql/apply_p3_sql.py")).resolve().parent


def run(w: WorkspaceClient, statement: str, params: dict[str, str]) -> list[list[str]]:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    args = ap.parse_args(argv)

    params = dict(p.split("=", 1) for p in args.param)
    w = WorkspaceClient()
    for name in args.files:
        path = Path(name)
        if not path.exists():
            path = SQL_DIR / name
        rows = run(w, path.read_text(), params)
        print(f"{path.name}: ok" + (f" -> {rows}" if rows else ""))
    return 0


if __name__ == "__main__":
    # A Databricks python task runs this under IPython, where a SystemExit --
    # even SystemExit(0) -- fails the task. Only a real failure exits.
    if (code := main()):
        raise SystemExit(code)
