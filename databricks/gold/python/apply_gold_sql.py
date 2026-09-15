#!/usr/bin/env python3
"""Run a gold-layer SQL file on the migration warehouse, with named parameters.

    python3 databricks/gold/python/apply_gold_sql.py sql/10_fct_subscription_mrr.sql \
        --param as_of_ts=2026-09-15T00:00:00

Each file holds exactly one statement, so the same text can be run here, stored in the
Databricks SQL query object the Lakeflow job task points at, and diffed between the two.
Parameters are passed as SQL parameter markers (`:as_of_ts`), never string-substituted, so a
value cannot change the shape of the statement.

Defaults for the two parameters the gold layer takes live in `defaults.json` next to the SQL
so the job, this runner and the reconciliation all use the same numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

WAREHOUSE = "565cd2fd713738c4"
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
DEFAULTS = json.loads((SQL_DIR / "defaults.json").read_text())


def run(w: WorkspaceClient, statement: str, params: dict[str, str]) -> list[list[str]]:
    # Only the markers the statement actually mentions are bound: the warehouse rejects a
    # parameter that the statement does not use.
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
    data = result.result.data_array if result.result else []
    return data or []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    args = ap.parse_args(argv)

    params = dict(DEFAULTS)
    params.update(dict(p.split("=", 1) for p in args.param))

    w = WorkspaceClient()
    for name in args.files:
        path = Path(name)
        if not path.exists():
            path = SQL_DIR / name
        rows = run(w, path.read_text(), params)
        print(f"{path.name}: ok" + (f" -> {rows}" if rows else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
