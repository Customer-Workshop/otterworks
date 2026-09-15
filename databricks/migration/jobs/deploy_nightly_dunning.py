#!/usr/bin/env python3
"""Unit p1-job-nightly-dunning (U-25): deploy the converted nightly dunning job, PAUSED.

The legacy object is the DBMS_SCHEDULER job `JOB_NIGHTLY_DUNNING` (daily 02:00, DISABLED in
the source). Its converted form is the Lakeflow job `ow_tp_p1_nightly_dunning`: one
serverless Python task running `ow_tp_p1_nightly_dunning.py`, which calls the two converted
dunning procedures on Lakebase in one transaction.

What this program keeps from the source, and why:

  - the schedule is the same daily 02:00, as the quartz cron `0 0 2 * * ?` in UTC, and it
    is created PAUSED. The source job is disabled and every schedule this migration creates
    lands paused; enabling it is part of the owner's STOP E cutover decision;
  - `TRUNC(SYSDATE)` becomes the `as_of` job parameter, defaulting to
    `{{job.start_time.iso_date}}` - the run's own date in the schedule's timezone. An
    operator can replay a night by overriding it, which the legacy job could not do;
  - the Lakebase branch is the `lakebase_branch` parameter, defaulting to the wave branch.
    The task refuses `production` regardless of what is passed;
  - no notifications, no retries, no timeout. The legacy job reported nothing and retried
    nothing, and adding either here would be a behaviour change, not a conversion.

A SQL task is not an option: the converted procedures live in Lakebase Postgres, not in the
warehouse, so the body is a Python task that speaks the Postgres protocol. The task file is
uploaded to the workspace on every deploy, so the deployed text always matches the repo, and
the job is created once and `reset` afterwards so re-running converges on one job.

`--dry-run` prints the job definition and uploads nothing.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/migration/jobs/deploy_nightly_dunning.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as j
from databricks.sdk.service import workspace as ws

JOB_NAME = "ow_tp_p1_nightly_dunning"
# DBMS_SCHEDULER 'FREQ=DAILY;BYHOUR=2;BYMINUTE=0' as a quartz expression.
CRON = "0 0 2 * * ?"
TIMEZONE = "UTC"
TASK_FILE = Path(__file__).with_name("ow_tp_p1_nightly_dunning.py")
BRANCH_DEFAULT = "mig-p1-w2"
# The task talks to Lakebase over the Postgres protocol and mints its own credential.
DEPENDENCIES = ["psycopg[binary]==3.2.9", "databricks-sdk>=0.66.0"]


def job_settings(python_file: str) -> dict:
    return {
        "name": JOB_NAME,
        "description": ("U-25: nightly dunning schedule + suspension sweep, converted from "
                        "the legacy JOB_NIGHTLY_DUNNING. Calls billing.sp_schedule_dunning "
                        "then billing.sp_suspend_overdue on Lakebase in one transaction. "
                        "Created paused."),
        "parameters": [
            {"name": "as_of", "default": "{{job.start_time.iso_date}}"},
            {"name": "lakebase_branch", "default": BRANCH_DEFAULT},
        ],
        "tasks": [{
            "task_key": "nightly_dunning",
            "spark_python_task": {
                "python_file": python_file,
                "source": "WORKSPACE",
                "parameters": ["--as-of", "{{job.parameters.as_of}}",
                               "--lakebase-branch", "{{job.parameters.lakebase_branch}}"],
            },
            "environment_key": "dunning",
        }],
        "environments": [{
            "environment_key": "dunning",
            "spec": {"client": "3", "dependencies": DEPENDENCIES},
        }],
        "schedule": {"quartz_cron_expression": CRON, "timezone_id": TIMEZONE,
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
    }


def upload_task(w: WorkspaceClient, parent_path: str) -> str:
    w.workspace.mkdirs(parent_path)
    remote = f"{parent_path}/{TASK_FILE.name}"
    w.workspace.upload(remote, TASK_FILE.read_bytes(), format=ws.ImportFormat.AUTO,
                       overwrite=True)
    return remote


def _typed(settings: dict) -> dict:
    """The create call takes typed keyword arguments, not the settings dict."""
    parsed = j.JobSettings.from_dict(settings)
    return {"name": parsed.name, "description": parsed.description,
            "parameters": parsed.parameters, "tasks": parsed.tasks,
            "environments": parsed.environments, "schedule": parsed.schedule,
            "max_concurrent_runs": parsed.max_concurrent_runs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.dry_run:
        print(json.dumps(job_settings("/Workspace/<path>/" + TASK_FILE.name), indent=2))
        return 0

    w = WorkspaceClient()
    parent_path = f"/Users/{w.current_user.me().user_name}/ow_tp_migration"
    settings = job_settings(upload_task(w, parent_path))

    # A job name is not unique: an interrupted deploy can leave two jobs called this, and
    # resetting one of them would leave the other scheduling dunning attempts of its own.
    matches = [job for job in w.jobs.list(name=JOB_NAME)
               if job.settings and job.settings.name == JOB_NAME]
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} jobs are named {JOB_NAME} "
                         f"({', '.join(str(m.job_id) for m in matches)}); "
                         "delete the duplicates before deploying")
    existing = matches[0] if matches else None
    if existing is None:
        job_id = w.jobs.create(**_typed(settings)).job_id
        action = "created"
    else:
        job_id = existing.job_id
        w.jobs.reset(job_id=job_id, new_settings=j.JobSettings.from_dict(settings))
        action = "updated"

    state = w.jobs.get(job_id=job_id)
    print(json.dumps({"job": JOB_NAME, "job_id": job_id, "action": action,
                      "schedule": state.settings.schedule.as_dict(),
                      "parameters": [p.as_dict() for p in state.settings.parameters]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
