#!/usr/bin/env python3
"""Deploy the cnvorch orchestration unit to the shared demo Databricks workspace.

Imports the four orchestration notebooks at the contract paths
/Shared/ow_tp/orchestrate_{ingest,parse,publish_psv,finance}_cnvorch, imports
the composed sibling units' sources BYTE-IDENTICAL (verified against the
merged files under etl/databricks/cnvingest and etl/databricks/cnvparse)
under /Shared/ow_tp/cnvorch/, and creates (or resets) the
ow_tp_orchestrate_cnvorch job from job_ow_tp_orchestrate_cnvorch.json.
Live execution belongs to the parent session's validation window; this
script only makes that run possible.

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

WORKSPACE_DIR = "/Shared/ow_tp"
VENDOR_DIR = f"{WORKSPACE_DIR}/cnvorch"
JOB_NAME = "ow_tp_orchestrate_cnvorch"

NOTEBOOKS = [
    ("orchestrate_ingest_cnvorch_notebook.py", f"{WORKSPACE_DIR}/orchestrate_ingest_cnvorch", "SOURCE"),
    ("orchestrate_parse_cnvorch_notebook.py", f"{WORKSPACE_DIR}/orchestrate_parse_cnvorch", "SOURCE"),
    ("orchestrate_publish_psv_cnvorch_notebook.py", f"{WORKSPACE_DIR}/orchestrate_publish_psv_cnvorch", "SOURCE"),
    ("orchestrate_finance_cnvorch_notebook.py", f"{WORKSPACE_DIR}/orchestrate_finance_cnvorch", "SOURCE"),
]

# Composed sibling sources, imported verbatim from their merged unit dirs.
VENDORED = [
    (REPO_ROOT / "etl/databricks/cnvingest/sftp_ingest_poll_notebook.py", f"{VENDOR_DIR}/cnvingest/sftp_ingest_poll_notebook", "SOURCE", "PYTHON"),
    (REPO_ROOT / "etl/databricks/cnvingest/ingest_core.py", f"{VENDOR_DIR}/cnvingest/ingest_core.py", "AUTO", "PYTHON"),
    (REPO_ROOT / "etl/databricks/cnvparse/pipeline_parse_custbill.sql", f"{VENDOR_DIR}/cnvparse/pipeline_parse_custbill.sql", "AUTO", None),
    (REPO_ROOT / "etl/databricks/cnvfinance/finance_excel_report_notebook.py", f"{VENDOR_DIR}/cnvfinance/finance_excel_report_notebook", "SOURCE", "PYTHON"),
    (REPO_ROOT / "etl/databricks/cnvfinance/finance_core.py", f"{VENDOR_DIR}/cnvfinance/finance_core.py", "AUTO", "PYTHON"),
]


def import_source(dbx: Databricks, local: Path, workspace_path: str, fmt: str, language: str | None = "PYTHON") -> None:
    payload = {
        "path": workspace_path,
        "format": fmt,
        "overwrite": True,
        "content": base64.b64encode(local.read_bytes()).decode("ascii"),
    }
    if language:
        payload["language"] = language
    dbx.ok("POST", "/api/2.0/workspace/import", payload)
    print(f"imported {workspace_path} ({fmt})")


def main() -> int:
    dbx = Databricks()
    for d in (WORKSPACE_DIR, f"{VENDOR_DIR}/cnvingest", f"{VENDOR_DIR}/cnvparse", f"{VENDOR_DIR}/cnvfinance"):
        dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": d})
    for fname, path, fmt in NOTEBOOKS:
        import_source(dbx, HERE / fname, path, fmt)
    for local, path, fmt, language in VENDORED:
        import_source(dbx, local, path, fmt, language)
    spec = json.loads((HERE / "job_ow_tp_orchestrate_cnvorch.json").read_text())
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
