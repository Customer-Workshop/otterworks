#!/usr/bin/env python3
"""Deploy and run the bronze_wide notebook on serverless compute.

Used to produce recon evidence before the parent applies
`infrastructure/terraform-databricks/jobs_bronze_wide.tf`.  It imports the
notebook under `/Shared/ow_tp` and submits a one-off serverless notebook run:
no cluster, warehouse or any other hourly-cost resource is created.

Usage:
    python3 run_notebook.py --ns demo
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parent / "ow_tp_bronze_wide.py"
WORKSPACE_PATH = "/Shared/ow_tp/ow_tp_bronze_wide"


def api(method: str, path: str, body: dict | None = None) -> dict:
    host = (os.environ.get("DATABRICKS_HOST") or os.environ["DATABRICKS_DEMO_HOST"]).rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN") or os.environ["DATABRICKS_DEMO_TOKEN"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{host}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:800]}") from exc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    api("POST", "/api/2.0/workspace/mkdirs", {"path": "/Shared/ow_tp"})
    api("POST", "/api/2.0/workspace/import", {
        "path": WORKSPACE_PATH, "format": "SOURCE", "language": "PYTHON",
        "overwrite": True,
        "content": base64.b64encode(NOTEBOOK.read_bytes()).decode(),
    })

    run = api("POST", "/api/2.2/jobs/runs/submit", {
        "run_name": f"ow_tp_bronze_wide_adhoc_{args.ns}",
        "tasks": [{
            "task_key": "load_bronze_wide",
            "notebook_task": {"notebook_path": WORKSPACE_PATH,
                              "base_parameters": {"ns": args.ns}},
        }],
    })
    run_id = run["run_id"]
    print(f"submitted run {run_id}")
    deadline = time.time() + args.timeout
    while True:
        state = api("GET", f"/api/2.2/jobs/runs/get?run_id={run_id}")
        life = state.get("state", {}).get("life_cycle_state")
        if life in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            break
        if time.time() > deadline:
            raise SystemExit(f"run {run_id} still {life} after {args.timeout}s")
        time.sleep(15)
    task_run_id = state["tasks"][0]["run_id"]
    out = api("GET", f"/api/2.1/jobs/runs/get-output?run_id={task_run_id}")
    print(json.dumps({"run_id": run_id, "state": state["state"],
                      "run_page_url": state.get("run_page_url")}, indent=2))
    if out.get("error"):
        print(out["error"])
        print((out.get("error_trace") or "")[-4000:])
        return 1
    print(out.get("notebook_output", {}).get("result", ""))
    return 0 if state["state"].get("result_state") == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
