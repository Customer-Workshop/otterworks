#!/usr/bin/env python3
"""Deploy the cnvfinance finance-report unit to the shared demo Databricks workspace.

Imports the notebook + core module under /Shared/ow_tp/cnvfinance/ and
creates (or resets) the ow_tp_finance_cnvfinance job from
job_ow_tp_finance_cnvfinance.json. Live execution belongs to the parent
session's validation window; this script only makes that run possible.

Requires DATABRICKS_DEMO_HOST / DATABRICKS_DEMO_TOKEN in the environment
(referenced by name only; values are never printed).
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.append(str(REPO_ROOT / "scripts" / "tp_dbx"))
from client import Databricks  # noqa: E402

WORKSPACE_DIR = "/Shared/ow_tp/cnvfinance"
JOB_NAME = "ow_tp_finance_cnvfinance"


def import_source(dbx: Databricks, local: Path, workspace_path: str, fmt: str) -> None:
    dbx.ok(
        "POST",
        "/api/2.0/workspace/import",
        {
            "path": workspace_path,
            "format": fmt,
            "language": "PYTHON",
            "overwrite": True,
            "content": base64.b64encode(local.read_bytes()).decode("ascii"),
        },
    )
    print(f"imported {workspace_path} ({fmt})")


def main() -> int:
    dbx = Databricks()
    dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": WORKSPACE_DIR})
    import_source(
        dbx,
        HERE / "finance_excel_report_notebook.py",
        f"{WORKSPACE_DIR}/finance_excel_report_notebook",
        "SOURCE",
    )
    import_source(
        dbx,
        HERE / "finance_core.py",
        f"{WORKSPACE_DIR}/finance_core.py",
        "AUTO",
    )
    spec = json.loads((HERE / "job_ow_tp_finance_cnvfinance.json").read_text())
    existing = [
        job
        for job in dbx.list_all(f"/api/2.2/jobs/list?name={JOB_NAME}", "jobs")
        if job.get("settings", {}).get("name") == JOB_NAME
    ]
    if existing:
        job_id = existing[0]["job_id"]
        dbx.ok("POST", "/api/2.2/jobs/reset", {"job_id": job_id, "new_settings": spec})
        print(f"reset job {JOB_NAME} (job_id={job_id})")
    else:
        job_id = dbx.ok("POST", "/api/2.2/jobs/create", spec)["job_id"]
        print(f"created job {JOB_NAME} (job_id={job_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
