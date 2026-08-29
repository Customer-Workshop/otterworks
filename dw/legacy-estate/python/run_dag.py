"""Run the local, Airflow-shaped legacy DAG with the shared ELT runner."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(ROOT / "dw/legacy-estate/jobs"))
from legacy_dw_dag import build_dag  # noqa: E402

RUNNER = ROOT / "dw/legacy-estate/python/runner.py"
INVOKER = ROOT / "dw/legacy-estate/python/invoke_proc.py"
AUDITOR = ROOT / "dw/legacy-estate/python/write_load_audit.py"
DEFAULT_DSN = (
    "host=127.0.0.1 port=15432 dbname=analytics_dw "
    "user=dw_admin password=dw_local_dev sslmode=disable"
)


def _ordered_tasks(tasks):
    remaining = {task.task_id: task for task in tasks}
    completed: set[str] = set()
    while remaining:
        ready = [
            task for task in remaining.values()
            if set(task.upstream) <= completed
        ]
        if not ready:
            raise RuntimeError("DAG contains a dependency cycle")
        for task in ready:
            yield task
            completed.add(task.task_id)
            del remaining[task.task_id]


def _table_for(task_id: str) -> str | None:
    if task_id in {"merge_customer_scd2", "load_orders_incremental", "refresh_marts", "housekeeping"}:
        return None
    schema = "core" if task_id in {
        "dim_customer_scd2", "dim_product", "dim_date", "dim_store", "fct_orders",
        "fct_order_items", "fct_web_events", "fct_returns", "fx_rates_daily",
    } else "mart"
    return f"{schema}.{task_id}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dag", default="legacy_dw_nightly")
    parser.add_argument("--dsn", default=os.environ.get("DW_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument(
        "--audit",
        type=Path,
        default=ROOT / "dw/harness/runtime/load-audit.jsonl",
    )
    args = parser.parse_args()
    dag = build_dag()
    if args.dag != dag.dag_id:
        raise SystemExit(f"unknown DAG: {args.dag}")

    environment = {**os.environ, "DW_POSTGRES_DSN": args.dsn}
    for task in _ordered_tasks(dag.tasks):
        if task.command.startswith("CALL "):
            procedure = task.command.removeprefix("CALL ").removesuffix("()")
            command = [sys.executable, str(INVOKER), "--procedure", procedure]
        else:
            table = _table_for(task.task_id)
            if table is None:
                raise RuntimeError(f"missing table mapping for {task.task_id}")
            command = [
                sys.executable,
                str(RUNNER),
                "--script",
                str(ROOT / "dw/legacy-estate" / task.command),
                "--table",
                table,
                "--dsn",
                args.dsn,
            ]
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
        if (table := _table_for(task.task_id)) is not None:
            subprocess.run(
                [
                    sys.executable,
                    str(AUDITOR),
                    "--table",
                    table,
                    "--out",
                    str(args.audit),
                    "--dsn",
                    args.dsn,
                ],
                cwd=ROOT,
                env=environment,
                check=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
