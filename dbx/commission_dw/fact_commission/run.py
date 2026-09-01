#!/usr/bin/env python3
"""Run, deploy, or trigger the COMMISSION_DW fact-and-summary Workflow."""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts" / "tp_dbx"))
from client import Databricks, DbxError, require_ns

PERIOD_MONTH_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
UNIT = "fact_commission"
WAREHOUSE = "565cd2fd713738c4"
NS_BOUND = {
    "ow_tp.silver.fact_commission_cdw": "ow_tp.silver.fact_commission_{ns}",
    "ow_tp.ops.run_log_cdw": "ow_tp.ops.run_log_{ns}",
    "ow_tp.ops.quarantine_cdw": "ow_tp.ops.quarantine_{ns}",
    "ow_tp.bronze.commission_ledger_cdw": "ow_tp.bronze.commission_ledger_{ns}",
    "ow_tp.bronze.policies_cdw": "ow_tp.bronze.policies_{ns}",
    "ow_tp.silver.dim_agent_cdw": "ow_tp.silver.dim_agent_{ns}",
    "ow_tp.silver.dim_product_cdw": "ow_tp.silver.dim_product_{ns}",
    "ow_tp.silver.dim_period_cdw": "ow_tp.silver.dim_period_{ns}",
    "/cdw/": "/{ns}/",
    "_cdw": "_{ns}",
}
UPLOADS = (
    "scripts/tp_dbx/client.py",
    "scripts/tp_dbx/cdw_baseline.py",
    "etl/legacy-extra/commission_dw/cdw/manifest.json",
    "dbx/commission_dw/dim_agent/run.py",
    "dbx/commission_dw/dim_agent/ddl.sql",
    "dbx/commission_dw/dim_agent/load.sql",
    "dbx/commission_dw/dim_product/run.py",
    "dbx/commission_dw/dim_product/ddl.sql",
    "dbx/commission_dw/dim_product/load.sql",
    "dbx/commission_dw/dim_period/run.py",
    "dbx/commission_dw/dim_period/ddl.sql",
    "dbx/commission_dw/dim_period/load.sql",
    "dbx/commission_dw/fact_commission/run.py",
    "dbx/commission_dw/fact_commission/ddl.sql",
    "dbx/commission_dw/fact_commission/load.sql",
    "dbx/commission_dw/mv_agent_commission_summary/run.py",
    "dbx/commission_dw/mv_agent_commission_summary/ddl.sql",
    "dbx/commission_dw/mv_agent_commission_summary/load.sql",
)
DRIVER_NOTEBOOK = """# Databricks notebook source
import os
import subprocess
import sys

dbutils.widgets.text("task", "feed_refresh")
dbutils.widgets.text("ns", "cdw")
dbutils.widgets.text("period_month", "")
dbutils.widgets.text("run_id", "")
task = dbutils.widgets.get("task")
ns = dbutils.widgets.get("ns")
period_month = dbutils.widgets.get("period_month")
run_id = dbutils.widgets.get("run_id")
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
env = dict(os.environ, DATABRICKS_DEMO_HOST=ctx.apiUrl().get(), DATABRICKS_DEMO_TOKEN=ctx.apiToken().get())
SRC = "/Workspace/Shared/ow_tp/cdw/src"
cmds = {
  "feed_refresh": ["scripts/tp_dbx/cdw_baseline.py", "load-feed", "--ns", ns],
  "dim_agent": ["dbx/commission_dw/dim_agent/run.py", "--ns", ns],
  "dim_product": ["dbx/commission_dw/dim_product/run.py", "--ns", ns],
  "dim_period": ["dbx/commission_dw/dim_period/run.py", "--ns", ns],
  "fact_commission": ["dbx/commission_dw/fact_commission/run.py", "--ns", ns, "--run-id", run_id] + (["--period-month", period_month] if period_month else []),
  "mv_agent_commission_summary": ["dbx/commission_dw/mv_agent_commission_summary/run.py", "--ns", ns],
}
if task not in cmds:
    raise ValueError(f"unknown task: {task}")
proc = subprocess.run([sys.executable] + cmds[task], cwd=SRC, env=env, capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
if proc.returncode != 0:
    raise RuntimeError(f"{task} failed rc={proc.returncode}")
"""


def statements(path: Path, ns: str, substitutions: dict[str, str] | None = None) -> list[str]:
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("--"))
    for literal, template in NS_BOUND.items():
        text = text.replace(literal, template.format(ns=ns))
    for literal, value in (substitutions or {}).items():
        text = text.replace(literal, value)
    chunks: list[str] = []
    start = 0
    quoted = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif char == ";" and not quoted:
            chunk = text[start:index].strip()
            if chunk:
                chunks.append(chunk)
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def sql_literal(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"cdw-{stamp}-{uuid.uuid4().hex[:8]}"


def merge_metrics(result) -> tuple[int, int, int]:
    values = result.dicts()[0] if result.rows else {}
    try:
        return (
            int(values["num_affected_rows"]),
            int(values["num_updated_rows"]),
            int(values["num_inserted_rows"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DbxError(f"MERGE result did not include row metrics: {values}") from exc


def insert_run_log(dbx: Databricks, ns: str, run: str, period: str | None, merged: int | None,
                   updated: int | None, inserted: int | None, dropped: int, status: str,
                   detail: str | None, started: str) -> None:
    table = NS_BOUND["ow_tp.ops.run_log_cdw"].format(ns=ns)
    detail_sql = sql_literal(detail[:500].replace("\n", " ") if detail else None)
    statement = (
        f"INSERT INTO {table} VALUES ({sql_literal(run)}, 'fact_commission', {sql_literal(period)}, "
        f"{'NULL' if merged is None else merged}, {'NULL' if updated is None else updated}, "
        f"{'NULL' if inserted is None else inserted}, {dropped}, {sql_literal(status)}, {detail_sql}, "
        f"TIMESTAMP '{started}', current_timestamp())"
    )
    dbx.sql_ok(statement)


def execute_load(dbx: Databricks, ns: str, period: str | None, run: str, started: str) -> None:
    substitutions = {"__RUN_ID__": run, "__PERIOD_MONTH__": sql_literal(period)}
    dropped = 0
    merged = updated = inserted = None
    try:
        for statement in statements(HERE / "ddl.sql", ns):
            dbx.sql_ok(statement)
        for statement in statements(HERE / "load.sql", ns, substitutions):
            result = dbx.sql_ok(statement)
            upper = statement.lstrip().upper()
            if upper.startswith("SELECT COUNT(*) AS DROPPED_JOIN_ROWS"):
                dropped = int(result.scalar() or 0)
                if dropped:
                    detail = f"fact_commission: {dropped} ledger rows dropped by inner joins"
                    insert_run_log(dbx, ns, run, period, None, None, None, dropped, "FAILED", detail, started)
                    raise DbxError(detail)
            elif upper.startswith("MERGE INTO"):
                merged, updated, inserted = merge_metrics(result)
        insert_run_log(dbx, ns, run, period, merged, updated, inserted, dropped, "SUCCEEDED", None, started)
    except Exception as exc:
        if not (dropped and isinstance(exc, DbxError)):
            try:
                insert_run_log(dbx, ns, run, period, merged, updated, inserted, dropped,
                               "FAILED", str(exc), started)
            except Exception:  # noqa: BLE001
                sys.stderr.write("unable to write FAILED run_log row\n")
        raise


def deploy(dbx: Databricks, ns: str) -> int:
    base = f"/Shared/ow_tp/{ns}/src"
    for relative in UPLOADS:
        destination = f"{base}/{relative}"
        dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": destination.rsplit("/", 1)[0]})
        payload = base64.b64encode((REPO / relative).read_bytes()).decode()
        dbx.ok("POST", "/api/2.0/workspace/import", {
            "path": destination, "format": "AUTO", "overwrite": True, "content": payload,
        })
    notebook_path = f"/Shared/ow_tp/{ns}/load_commission_facts"
    notebook = DRIVER_NOTEBOOK.replace("/cdw/", f"/{ns}/").replace("_cdw", f"_{ns}")
    dbx.import_notebook(notebook_path, notebook, language="PYTHON")
    settings = json.loads((HERE / "job.json").read_text(encoding="utf-8"))
    settings_text = json.dumps(settings).replace("cdw", ns)
    job_id = dbx.upsert_job(json.loads(settings_text))
    job = dbx.ok("GET", f"/api/2.1/jobs/get?job_id={job_id}")
    schedule = job.get("settings", {}).get("schedule", {})
    print(f"job_id={job_id} url={dbx.host}/jobs/{job_id} pause_status={schedule.get('pause_status')}")
    return 0


def run_job(dbx: Databricks, ns: str, period: str | None) -> int:
    name = f"ow_tp_{ns}_load_commission_facts"
    job = dbx.find_job(name)
    if not job:
        raise SystemExit(f"job not found: {name}")
    run = dbx.run_job(int(job["job_id"]), {"ns": ns, "period_month": period or ""})
    result = dbx.wait_run(run, timeout_s=1800)
    state = result.get("state", {})
    print(f"run_id={run} result_state={state.get('result_state')} url={dbx.run_url(run)}")
    for task in result.get("tasks", []):
        task_state = task.get("state", {})
        print(f"task={task.get('task_key')} life_cycle_state={task_state.get('life_cycle_state')} "
              f"result_state={task_state.get('result_state')}")
    return 0 if state.get("result_state") == "SUCCESS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--deploy", action="store_true")
    mode.add_argument("--run-job", action="store_true")
    parser.add_argument("--ns", default="cdw")
    parser.add_argument("--period-month")
    parser.add_argument("--run-id")
    parser.add_argument("--warehouse", default=WAREHOUSE)
    args = parser.parse_args()
    ns = require_ns(args.ns)
    if args.period_month is not None and not PERIOD_MONTH_RE.fullmatch(args.period_month):
        raise SystemExit("--period-month must match YYYY-MM")
    dbx = Databricks(warehouse_id=args.warehouse)
    if args.deploy:
        return deploy(dbx, ns)
    if args.run_job:
        return run_job(dbx, ns, args.period_month)
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    execute_load(dbx, ns, args.period_month, args.run_id or run_id(), started)
    target = NS_BOUND["ow_tp.silver.fact_commission_cdw"].format(ns=ns)
    print(f"rows in {target}: {dbx.sql_ok(f'SELECT count(*) FROM {target}').scalar()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
