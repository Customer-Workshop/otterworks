#!/usr/bin/env python3
"""Unit p1-job-purge-audit-log (U-26): deploy the converted retention job, PAUSED.

The legacy object is a DBMS_SCHEDULER job, `JOB_PURGE_AUDIT_LOG`, that deletes
`billing_audit_log` rows older than 90 days at 03:30 daily and swallows every error. Its
converted form is the Lakeflow job `ow_tp_p1_purge_audit_log`: one SQL task on the
migration warehouse running `ow_tp_p1_purge_audit_log.sql`, whose text is the converted
PL/SQL block (retention parameter, `WHEN OTHERS THEN NULL` reproduced as an EXIT handler).

What this program keeps from the source, and why:

  - the schedule is the same 03:30 daily, expressed as the quartz cron `0 30 3 * * ?` in
    UTC, and it is created PAUSED. The Oracle job is DISABLED in the source and every
    schedule this migration creates lands paused, so nothing starts running on its own;
  - the 90 days stay 90 days but stop being a constant buried in the job text: they are
    the `retention_days` job parameter, default `90`, passed into the SQL task. An
    operator can change the window without editing converted code;
  - no notifications and no retries are configured. The legacy job told nobody when it
    failed, and adding an alert here would be a behaviour change, not a conversion.

The job is created once and updated in place afterwards (`reset`), so re-running this
program converges on one job rather than piling up duplicates. The SQL text lives in a
Databricks SQL query object of the same name; the query is the task's body, and it is
rewritten from the file on every deploy so the deployed text always matches the repo.

`--dry-run` prints the job definition without touching the workspace.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/migration/jobs/deploy_purge_audit_log.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as j
from databricks.sdk.service import sql as sqlsvc

JOB_NAME = "ow_tp_p1_purge_audit_log"
QUERY_NAME = "ow_tp_p1_purge_audit_log"
WAREHOUSE = "565cd2fd713738c4"
RETENTION_DEFAULT = "90"
# DBMS_SCHEDULER 'FREQ=DAILY;BYHOUR=3;BYMINUTE=30' as a quartz expression.
CRON = "0 30 3 * * ?"
TIMEZONE = "UTC"
SQL_FILE = Path(__file__).with_name("ow_tp_p1_purge_audit_log.sql")


def upsert_query(w: WorkspaceClient, text: str, parent_path: str) -> str:
    # A display name is not an identity in Databricks: another principal can own a visible
    # query of the same name. Match on the folder this program deploys into as well, and
    # refuse to guess when more than one query still matches.
    # the list response carries no parent_path, so each name match is read back in full;
    # the service echoes the folder with a `/Workspace` prefix the create call does not take
    named = [w.queries.get(id=q.id) for q in w.queries.list(page_size=100)
             if q.display_name == QUERY_NAME]
    matches = [q for q in named
               if (q.parent_path or "").removeprefix("/Workspace") == parent_path]
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} queries named {QUERY_NAME} under {parent_path}: "
                         "refusing to pick one")
    existing = matches[0] if matches else None
    if existing is None:
        created = w.queries.create(query=sqlsvc.CreateQueryRequestQuery(
            display_name=QUERY_NAME, query_text=text, warehouse_id=WAREHOUSE,
            parent_path=parent_path,
            description="Converted body of the legacy JOB_PURGE_AUDIT_LOG (U-26)",
            parameters=[sqlsvc.QueryParameter(
                name="retention_days", title="retention_days",
                text_value=sqlsvc.TextValue(value=RETENTION_DEFAULT))]))
        return created.id
    w.queries.update(id=existing.id, update_mask="query_text,warehouse_id",
                     query=sqlsvc.UpdateQueryRequestQuery(query_text=text,
                                                          warehouse_id=WAREHOUSE))
    return existing.id


def job_settings(query_id: str) -> dict:
    return {
        "name": JOB_NAME,
        "description": ("U-26: retention purge for ow_tp.silver.billing_audit_log, "
                        "converted from the legacy JOB_PURGE_AUDIT_LOG. Created paused."),
        "parameters": [{"name": "retention_days", "default": RETENTION_DEFAULT}],
        "tasks": [{
            "task_key": "purge_audit_log",
            "sql_task": {
                "query": {"query_id": query_id},
                "warehouse_id": WAREHOUSE,
                "parameters": {"retention_days": "{{job.parameters.retention_days}}"},
            },
        }],
        "schedule": {"quartz_cron_expression": CRON, "timezone_id": TIMEZONE,
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    text = SQL_FILE.read_text()
    if args.dry_run:
        print(json.dumps(job_settings("<query_id>"), indent=2))
        print(text)
        return 0

    w = WorkspaceClient()
    parent_path = f"/Users/{w.current_user.me().user_name}"
    query_id = upsert_query(w, text, parent_path)
    settings = job_settings(query_id)

    existing = next((job for job in w.jobs.list(name=JOB_NAME) if job.settings
                     and job.settings.name == JOB_NAME), None)
    if existing is None:
        job_id = w.jobs.create(**{k: v for k, v in _typed(settings).items()}).job_id
        action = "created"
    else:
        job_id = existing.job_id
        w.jobs.reset(job_id=job_id, new_settings=j.JobSettings.from_dict(settings))
        action = "updated"

    state = w.jobs.get(job_id=job_id)
    print(json.dumps({"job": JOB_NAME, "job_id": job_id, "action": action,
                      "query_id": query_id,
                      "schedule": state.settings.schedule.as_dict(),
                      "parameters": [p.as_dict() for p in state.settings.parameters]},
                     indent=2))
    return 0


def _typed(settings: dict) -> dict:
    """The create call takes typed keyword arguments, not the settings dict."""
    parsed = j.JobSettings.from_dict(settings)
    return {"name": parsed.name, "description": parsed.description,
            "parameters": parsed.parameters, "tasks": parsed.tasks,
            "schedule": parsed.schedule,
            "max_concurrent_runs": parsed.max_concurrent_runs}


if __name__ == "__main__":
    raise SystemExit(main())
