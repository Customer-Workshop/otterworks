#!/usr/bin/env python3
"""Deploy and execute the bronze_hist notebook on serverless job compute.

Terraform (`infrastructure/terraform-databricks/jobs_bronze_hist.tf`) owns the
durable `ow_tp_bronze_hist` job and is applied centrally. To exercise the unit
before that apply, this submits the same notebook as a one-time run with the
same parameters: serverless task compute, nothing durable created, no cluster
and no warehouse.

    python3 scripts/tp_databricks/bronze_hist_run.py --ns demo --runs 2

Two runs is the default because restart safety is the claim under test: the
second run must merge the identical input to a no-op.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_dbx.client import Databricks, DbxError, require_ns  # noqa: E402

UNIT = "bronze_hist"
NOTEBOOK_SOURCE = REPO_ROOT / "pipelines" / "ow_tp" / UNIT / "bronze_hist_load.py"
NOTEBOOK_ROOT = "/Shared/ow_tp"


def submit(dbx: Databricks, notebook_path: str, ns: str, catalog: str, landing_root: str) -> dict:
    """One-time run of the notebook task. No cluster spec means serverless."""
    body = {
        "run_name": f"ow_tp_{UNIT}_oneshot_{ns}",
        "timeout_seconds": 3600,
        "tasks": [{
            "task_key": "load_hist",
            "notebook_task": {
                "notebook_path": notebook_path,
                "base_parameters": {"ns": ns, "catalog": catalog, "landing_root": landing_root},
            },
        }],
    }
    run_id = int(dbx.ok("POST", "/api/2.1/jobs/runs/submit", body)["run_id"])
    print(f"[run] submitted {run_id}: {dbx.run_url(run_id)}")
    run = dbx.wait_run(run_id, timeout_s=3600)
    state = run.get("state", {})
    result = {
        "run_id": run_id,
        "url": dbx.run_url(run_id),
        "result_state": state.get("result_state"),
        "state_message": state.get("state_message", ""),
    }
    task_runs = run.get("tasks") or []
    if task_runs:
        output = dbx.ok("GET", f"/api/2.1/jobs/runs/get-output?run_id={task_runs[0]['run_id']}")
        notebook_output = (output.get("notebook_output") or {}).get("result")
        if notebook_output:
            result["notebook_output"] = json.loads(notebook_output)
        elif output.get("error"):
            result["error"] = output["error"]
            result["error_trace"] = (output.get("error_trace") or "")[-2000:]
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--catalog", default="ow_tp")
    ap.add_argument("--landing-root", default="/Volumes/ow_tp/bronze/landing")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out", default=str(REPO_ROOT / ".tp-preflight" / "bronze_hist_runs.json"))
    args = ap.parse_args()

    ns = require_ns(args.ns)
    if not args.catalog.startswith("ow_tp"):
        raise SystemExit("refusing to target a catalog outside the ow_tp prefix")

    dbx = Databricks()
    notebook_path = f"{NOTEBOOK_ROOT}/{UNIT}_load"
    dbx.import_notebook(notebook_path, NOTEBOOK_SOURCE.read_text(encoding="utf-8"))
    print(f"[run] deployed {notebook_path}")

    results = []
    for attempt in range(1, args.runs + 1):
        print(f"[run] execution {attempt}/{args.runs}")
        result = submit(dbx, notebook_path, ns, args.catalog, args.landing_root.rstrip("/"))
        results.append(result)
        print(json.dumps(result, indent=2)[:2000])
        if result["result_state"] != "SUCCESS":
            Path(args.out).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            raise DbxError(f"run {result['run_id']} finished {result['result_state']}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"[run] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
