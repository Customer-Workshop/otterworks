#!/usr/bin/env python3
"""Deploy, trigger, or inspect the draft COMMISSION_DW parallel-run Workflow."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts" / "tp_dbx"))
from client import Databricks, require_ns

WAREHOUSE = "565cd2fd713738c4"
JOB_NAME = "ow_tp_cdw_recon"
NOTEBOOK_PATH = "/Shared/ow_tp/cdw/recon"
NOTIFY_NOTEBOOK_PATH = "/Shared/ow_tp/cdw/recon_notify"
SECRET_SCOPE = "ow_tp_cdw"
WEBHOOK_URL_ENV = "DEVIN_CDW_WEBHOOK_URL"
WEBHOOK_SECRET_ENV = "DEVIN_CDW_WEBHOOK_SECRET"
SRC_ROOT = "/Shared/ow_tp/cdw/recon_src"
BASELINE_ROOT = "/Shared/ow_tp/cdw/recon_src/baseline"
REPORT_ROOT = "/Volumes/ow_tp/bronze/landing/{ns}/recon/{run_id}"
BASELINE_FILES = (
    "manifest.json",
    "AGENTS.csv",
    "PRODUCTS.csv",
    "POLICIES.csv",
    "COMMISSION_LEDGER.csv",
    "DIM_AGENT.csv",
    "DIM_PRODUCT.csv",
    "DIM_PERIOD.csv",
    "FACT_COMMISSION.csv",
    "MV_AGENT_COMMISSION_SUMMARY.csv",
)
UPLOADS = (
    "scripts/tp_dbx/client.py",
    "scripts/tp_dbx/cdw_recon.py",
    "dbx/commission_dw/dim_agent/run.py",
    "dbx/commission_dw/dim_agent/load.sql",
    "dbx/commission_dw/dim_agent/ddl.sql",
    "dbx/commission_dw/dim_product/run.py",
    "dbx/commission_dw/dim_product/load.sql",
    "dbx/commission_dw/dim_product/ddl.sql",
    "dbx/commission_dw/dim_period/run.py",
    "dbx/commission_dw/dim_period/load.sql",
    "dbx/commission_dw/dim_period/ddl.sql",
    "dbx/commission_dw/fact_commission/run.py",
    "dbx/commission_dw/fact_commission/load.sql",
    "dbx/commission_dw/fact_commission/ddl.sql",
    "dbx/commission_dw/mv_agent_commission_summary/run.py",
    "dbx/commission_dw/mv_agent_commission_summary/load.sql",
    "dbx/commission_dw/mv_agent_commission_summary/ddl.sql",
)

DRIVER_NOTEBOOK = """# Databricks notebook source
import json
import os
import subprocess
import sys

dbutils.widgets.text("task", "")
dbutils.widgets.text("ns", "cdw")
dbutils.widgets.text("staged_red", "false")
dbutils.widgets.text("run_id", "")
task = dbutils.widgets.get("task")
ns = dbutils.widgets.get("ns")
staged_red = dbutils.widgets.get("staged_red")
run_id = dbutils.widgets.get("run_id")
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
env = dict(os.environ, DATABRICKS_DEMO_HOST=ctx.apiUrl().get(),
           DATABRICKS_DEMO_TOKEN=ctx.apiToken().get())
SRC = "/Workspace/Shared/ow_tp/cdw/recon_src"
BASELINE = "/Workspace/Shared/ow_tp/cdw/recon_src/baseline"
OUT = f"/Volumes/ow_tp/bronze/landing/{ns}/recon/{run_id}/{task}"
if task not in {"fact_commission", "mv_agent_commission_summary"}:
    raise ValueError(f"unknown task: {task}")
os.chdir(SRC)
env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
rerun = f"python3 dbx/commission_dw/{task}/run.py --ns {ns}"
cmd = [
    sys.executable, "cdw_recon.py", "--unit", task, "--ns", ns,
    "--run-mode", "fixture", "--baseline-dir", BASELINE,
    "--rerun", rerun, "--out", OUT,
]
proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
if proc.returncode != 0:
    raise RuntimeError(f"{task} recon failed rc={proc.returncode}")
report_path = os.path.join(OUT, f"{task}.recon.json")
with open(report_path, encoding="utf-8") as report_file:
    report = json.load(report_file)
verdict = report.get("verdict")
if verdict is None:
    checks_pass = all(item.get("result") == "pass" for item in report["checks"])
    idem_pass = report["idempotency_rerun"].get("result") == "pass"
    verdict = "PASS" if checks_pass and idem_pass else "FAIL"
print(f"report={report_path} verdict={verdict}")
if verdict != "PASS":
    raise RuntimeError(f"{task} recon verdict was {verdict}")
if staged_red.lower() == "true":
    raise RuntimeError(
        f"STAGED RED RUN (verification of the remediation trigger) — recon verdict was {verdict}"
    )
"""

NOTIFY_NOTEBOOK = """# Databricks notebook source
# Final task (run_if ALL_DONE): forward the completed run to the remediation
# automation webhook. Secret-scope values are never printed.
import json
import urllib.request

dbutils.widgets.text("ns", "cdw")
dbutils.widgets.text("staged_red", "false")
dbutils.widgets.text("run_id", "")
dbutils.widgets.text("job_id", "")
ns = dbutils.widgets.get("ns")
run_id = dbutils.widgets.get("run_id")
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
host = ctx.apiUrl().get()
token = ctx.apiToken().get()
req = urllib.request.Request(
    f"{host}/api/2.1/jobs/runs/get?run_id={run_id}",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    run = json.load(resp)
tasks = {}
for task in run.get("tasks", []):
    key = task["task_key"]
    if key == "r3_notify":
        continue
    tasks[key] = {
        "result_state": task.get("state", {}).get("result_state"),
        "state_message": task.get("state", {}).get("state_message", ""),
    }
results = {t["result_state"] for t in tasks.values()}
verdict = "GREEN" if results == {"SUCCESS"} else "RED"
staged = any("STAGED RED RUN" in t["state_message"] for t in tasks.values())
payload = {
    "source": "databricks-jobs",
    "job_name": run.get("run_name"),
    "job_id": dbutils.widgets.get("job_id"),
    "run_id": run_id,
    "run_page_url": run.get("run_page_url"),
    "ns": ns,
    "verdict": verdict,
    "staged_red": staged or dbutils.widgets.get("staged_red").lower() == "true",
    "tasks": tasks,
    "reports": {
        key.split("_", 1)[1]: (
            f"/Volumes/ow_tp/bronze/landing/{ns}/recon/{run_id}/"
            f"{key.split('_', 1)[1]}/{key.split('_', 1)[1]}.recon.json"
        )
        for key in tasks
    },
}
url = dbutils.secrets.get("SECRET_SCOPE", "devin_webhook_url")
secret = dbutils.secrets.get("SECRET_SCOPE", "devin_webhook_secret")
hook = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "X-Webhook-Secret": secret},
    method="POST",
)
with urllib.request.urlopen(hook, timeout=60) as resp:
    print(f"webhook status={resp.status} verdict={verdict} staged_red={payload['staged_red']}")
    dbutils.notebook.exit(json.dumps({
        "webhook_status": resp.status,
        "verdict": verdict,
        "staged_red": payload["staged_red"],
    }))
""".replace("SECRET_SCOPE", SECRET_SCOPE)


def ensure_webhook_secrets(dbx: Databricks) -> bool:
    url = os.environ.get(WEBHOOK_URL_ENV)
    secret = os.environ.get(WEBHOOK_SECRET_ENV)
    if not url or not secret:
        return False
    scopes = dbx.ok("GET", "/api/2.0/secrets/scopes/list").get("scopes", [])
    if not any(s.get("name") == SECRET_SCOPE for s in scopes):
        dbx.ok("POST", "/api/2.0/secrets/scopes/create", {"scope": SECRET_SCOPE})
    for key, value in (("devin_webhook_url", url), ("devin_webhook_secret", secret)):
        dbx.ok("POST", "/api/2.0/secrets/put", {
            "scope": SECRET_SCOPE, "key": key, "string_value": value,
        })
    return True


def upload_file(dbx: Databricks, source: Path, destination: str) -> None:
    dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": destination.rsplit("/", 1)[0]})
    payload = base64.b64encode(source.read_bytes()).decode()
    dbx.ok("POST", "/api/2.0/workspace/import", {
        "path": destination,
        "format": "AUTO",
        "overwrite": True,
        "content": payload,
    })


def workspace_relative(relative: str) -> str:
    if relative.startswith("scripts/tp_dbx/"):
        return relative.removeprefix("scripts/tp_dbx/")
    return relative


def deploy(dbx: Databricks, ns: str, with_webhook: bool) -> int:
    source_settings = json.loads((HERE / "job.json").read_text(encoding="utf-8"))
    settings = json.loads(json.dumps(source_settings).replace("cdw", ns))
    existing = dbx.find_job(settings["name"])
    if existing:
        settings["schedule"]["pause_status"] = (
            existing.get("settings", {}).get("schedule", {}).get("pause_status", "PAUSED")
        )
    else:
        settings["schedule"]["pause_status"] = "PAUSED"
    if with_webhook and not ensure_webhook_secrets(dbx):
        raise SystemExit(
            f"--with-webhook needs {WEBHOOK_URL_ENV} and {WEBHOOK_SECRET_ENV} in the environment"
        )
    for relative in UPLOADS:
        destination = (
            f"{SRC_ROOT.replace('/cdw/', f'/{ns}/')}/{workspace_relative(relative)}"
        )
        upload_file(dbx, REPO / relative, destination)
    for filename in BASELINE_FILES:
        upload_file(
            dbx,
            REPO / "etl/legacy-extra/commission_dw/cdw" / filename,
            f"{BASELINE_ROOT.replace('/cdw/', f'/{ns}/')}/{filename}",
        )
    notebook_path = NOTEBOOK_PATH.replace("/cdw/", f"/{ns}/")
    dbx.import_notebook(
        notebook_path,
        DRIVER_NOTEBOOK.replace("/cdw/", f"/{ns}/"),
        language="PYTHON",
    )
    if with_webhook:
        dbx.import_notebook(
            NOTIFY_NOTEBOOK_PATH.replace("/cdw/", f"/{ns}/"),
            NOTIFY_NOTEBOOK,
            language="PYTHON",
        )
    job_id = dbx.upsert_job(settings)
    print(
        f"job_id={job_id} name={settings['name']} "
        f"pause_status={settings['schedule']['pause_status']} "
        f"webhook={'wired' if with_webhook else 'none'}"
    )
    return 0


def schedule(dbx: Databricks, ns: str, pause_status: str) -> int:
    job_name = JOB_NAME.replace("_cdw_", f"_{ns}_")
    job = dbx.find_job(job_name)
    if not job:
        raise SystemExit(f"job not found: {job_name}")
    job_id = int(job["job_id"])
    existing_schedule = dict(job.get("settings", {}).get("schedule", {}))
    existing_schedule["pause_status"] = pause_status
    dbx.ok("POST", "/api/2.1/jobs/update", {
        "job_id": job_id,
        "new_settings": {"schedule": existing_schedule},
    })
    updated = dbx.ok("GET", f"/api/2.1/jobs/get?job_id={job_id}")
    effective = updated.get("settings", {}).get("schedule", {}).get("pause_status")
    print(f"job_id={job_id} pause_status={effective}")
    return 0


def trigger(dbx: Databricks, ns: str, staged_red: bool) -> int:
    job_name = JOB_NAME.replace("_cdw_", f"_{ns}_")
    job = dbx.find_job(job_name)
    if not job:
        raise SystemExit(f"job not found: {job_name}")
    run_id = dbx.run_job(int(job["job_id"]), {
        "ns": ns,
        "staged_red": "true" if staged_red else "false",
    })
    result = dbx.wait_run(run_id, timeout_s=3600)
    state = result.get("state", {})
    print(f"run_id={run_id} result_state={state.get('result_state')} url={dbx.run_url(run_id)}")
    for task in result.get("tasks", []):
        task_key = task.get("task_key")
        task_state = task.get("state", {})
        if task_key == "r3_notify":
            print(
                f"task={task_key} life_cycle_state={task_state.get('life_cycle_state')} "
                f"result_state={task_state.get('result_state')}"
            )
            continue
        unit = task_key.removeprefix("r1_").removeprefix("r2_")
        report_path = f"{REPORT_ROOT.format(ns=ns, run_id=run_id)}/{unit}/{unit}.recon.json"
        print(
            f"task={task_key} life_cycle_state={task_state.get('life_cycle_state')} "
            f"result_state={task_state.get('result_state')} report={report_path}"
        )
    recon_ok = all(
        t.get("state", {}).get("result_state") == "SUCCESS"
        for t in result.get("tasks", []) if t.get("task_key") != "r3_notify"
    )
    return 0 if recon_ok else 1


def status(dbx: Databricks, ns: str) -> int:
    job_name = JOB_NAME.replace("_cdw_", f"_{ns}_")
    job = dbx.find_job(job_name)
    if not job:
        print(f"job not found: {job_name}")
        return 1
    job_id = int(job["job_id"])
    settings = job.get("settings", {})
    schedule = settings.get("schedule", {})
    print(
        f"job_id={job_id} name={settings.get('name')} "
        f"pause_status={schedule.get('pause_status')} "
        f"max_concurrent_runs={settings.get('max_concurrent_runs')}"
    )
    runs = dbx.ok("GET", f"/api/2.1/jobs/runs/list?job_id={job_id}&limit=10").get("runs", [])
    for run in runs:
        state = run.get("state", {})
        print(
            f"run_id={run.get('run_id')} life_cycle_state={state.get('life_cycle_state')} "
            f"result_state={state.get('result_state')} run_page_url={run.get('run_page_url')}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    deploy_parser = subparsers.add_parser("deploy", help="upload the draft assets and upsert the paused job")
    deploy_parser.add_argument("--ns", default="cdw")
    deploy_parser.add_argument("--warehouse", default=WAREHOUSE)
    deploy_parser.add_argument(
        "--with-webhook", action="store_true",
        help=f"add the r3_notify task; reads {WEBHOOK_URL_ENV}/{WEBHOOK_SECRET_ENV} into secret scope {SECRET_SCOPE}",
    )

    trigger_parser = subparsers.add_parser("trigger", help="run the paused job and print task results")
    trigger_parser.add_argument("--ns", default="cdw")
    trigger_parser.add_argument("--warehouse", default=WAREHOUSE)
    trigger_parser.add_argument("--staged-red", action="store_true")

    status_parser = subparsers.add_parser("status", help="show the paused job and recent runs")
    status_parser.add_argument("--ns", default="cdw")
    status_parser.add_argument("--warehouse", default=WAREHOUSE)

    schedule_parser = subparsers.add_parser(
        "schedule", help="pause or unpause the existing job"
    )
    schedule_parser.add_argument("--ns", default="cdw")
    schedule_parser.add_argument("--warehouse", default=WAREHOUSE)
    schedule_group = schedule_parser.add_mutually_exclusive_group(required=True)
    schedule_group.add_argument("--unpause", action="store_true")
    schedule_group.add_argument("--pause", action="store_true")

    args = parser.parse_args()
    ns = require_ns(args.ns)
    dbx = Databricks(warehouse_id=args.warehouse)
    if args.command == "deploy":
        return deploy(dbx, ns, args.with_webhook)
    if args.command == "trigger":
        return trigger(dbx, ns, args.staged_red)
    if args.command == "schedule":
        return schedule(dbx, ns, "UNPAUSED" if args.unpause else "PAUSED")
    return status(dbx, ns)


if __name__ == "__main__":
    raise SystemExit(main())
