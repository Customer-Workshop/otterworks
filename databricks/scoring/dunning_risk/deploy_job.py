#!/usr/bin/env python3
"""Deploy the Lakeflow job `ow_tp_dunning_risk`, PAUSED.

Six SQL tasks on the existing serverless warehouse, wired in the order the tables depend on
each other:

    features_invoice ──┬─> features_account ──┐
                       │                      ├─> score_account
                       ├─> score_invoice ─────┘
    rules ─────────────┤
                       └─> backtest

`rules` has no upstream because it is a literal table - it is the model - but both scoring
tasks depend on it, since they read their points out of it rather than hardcoding them.

Retries: every task gets 2 retries, 60s apart. Unlike the converted legacy jobs in
databricks/migration/jobs/, this one is new code with no legacy error-swallowing behaviour to
preserve, so a transient warehouse failure should be retried and a real failure should end
the run visibly rather than leaving a half-rebuilt set of tables.

The schedule is 04:00 UTC daily and lands PAUSED. Nothing about this job takes collections
action: it rebuilds tables that rank a queue, and the dunning process decides what to do.

The Lakebase publish is deliberately *not* a task here. It runs through
databricks/migration/lakebase/with_lakebase_dsn.py, which mints a short-lived credential only
after checking the branch against .migration/allowed_targets.json in the repo checkout.
Putting it in the job would mean reimplementing that credential path inside the workspace,
outside the allowlist check. See README.md.

`--dry-run` prints the job definition and the SQL without touching the workspace.

usage (with DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET set):
  python3 databricks/scoring/dunning_risk/deploy_job.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as j
from databricks.sdk.service import sql as sqlsvc

JOB_NAME = "ow_tp_dunning_risk"
WAREHOUSE = "565cd2fd713738c4"
CRON = "0 0 4 * * ?"
TIMEZONE = "UTC"
MAX_RETRIES = 2
RETRY_INTERVAL_MS = 60_000
SQL_DIR = Path(__file__).parent / "sql"

# (task_key, sql file, upstream task keys, whether the task takes the as_of parameter)
TASKS = [
    ("features_invoice", "01_features_invoice.sql", [], True),
    ("features_account", "02_features_account.sql", ["features_invoice"], False),
    ("rules", "03_rules.sql", [], False),
    ("score_invoice", "04_score_invoice.sql", ["features_invoice", "rules"], False),
    ("score_account", "05_score_account.sql", ["features_account", "score_invoice"], False),
    ("backtest", "06_backtest.sql", ["features_invoice", "rules"], False),
]

# Empty means "use the newest invoice date in the migrated history as the clock". See
# sql/01_features_invoice.sql for why that, and not the wall clock, is the honest default
# for a frozen extract.
AS_OF_DEFAULT = ""


def query_name(task_key: str) -> str:
    return f"{JOB_NAME}_{task_key}"


def upsert_query(w: WorkspaceClient, name: str, text: str, parent_path: str,
                 with_param: bool) -> str:
    # A display name is not an identity in Databricks, so match the deploy folder too and
    # refuse to guess when more than one query still matches.
    named = [w.queries.get(id=q.id) for q in w.queries.list(page_size=100)
             if q.display_name == name]
    matches = [q for q in named
               if (q.parent_path or "").removeprefix("/Workspace") == parent_path]
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} queries named {name} under {parent_path}: "
                         "refusing to pick one")
    params = [sqlsvc.QueryParameter(name="as_of", title="as_of",
                                    text_value=sqlsvc.TextValue(value=AS_OF_DEFAULT))] \
        if with_param else None
    if not matches:
        created = w.queries.create(query=sqlsvc.CreateQueryRequestQuery(
            display_name=name, query_text=text, warehouse_id=WAREHOUSE,
            parent_path=parent_path,
            description=f"{JOB_NAME}: {name.removeprefix(JOB_NAME + '_')}",
            parameters=params))
        return created.id
    w.queries.update(id=matches[0].id, update_mask="query_text,warehouse_id",
                     query=sqlsvc.UpdateQueryRequestQuery(query_text=text,
                                                          warehouse_id=WAREHOUSE))
    return matches[0].id


def job_settings(query_ids: dict[str, str]) -> dict:
    tasks = []
    for task_key, _, depends_on, with_param in TASKS:
        sql_task: dict = {"query": {"query_id": query_ids[task_key]},
                          "warehouse_id": WAREHOUSE}
        if with_param:
            sql_task["parameters"] = {"as_of": "{{job.parameters.as_of}}"}
        task: dict = {
            "task_key": task_key,
            "sql_task": sql_task,
            "max_retries": MAX_RETRIES,
            "min_retry_interval_millis": RETRY_INTERVAL_MS,
        }
        if depends_on:
            task["depends_on"] = [{"task_key": k} for k in depends_on]
        tasks.append(task)
    return {
        "name": JOB_NAME,
        "description": (
            "Rebuilds the dunning-risk features, rule set, scores and backtest in ow_tp. "
            "The score is an input to the dunning process, not an instruction: no task here "
            "schedules, sends, skips or suspends anything. Created paused."),
        "parameters": [{"name": "as_of", "default": AS_OF_DEFAULT}],
        "tasks": tasks,
        "schedule": {"quartz_cron_expression": CRON, "timezone_id": TIMEZONE,
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
    }


def _typed(settings: dict) -> dict:
    """The create call takes typed keyword arguments, not the settings dict."""
    parsed = j.JobSettings.from_dict(settings)
    return {"name": parsed.name, "description": parsed.description,
            "parameters": parsed.parameters, "tasks": parsed.tasks,
            "schedule": parsed.schedule,
            "max_concurrent_runs": parsed.max_concurrent_runs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.dry_run:
        print(json.dumps(job_settings({k: f"<{k}>" for k, _, _, _ in TASKS}), indent=2))
        return 0

    w = WorkspaceClient()
    parent_path = f"/Users/{w.current_user.me().user_name}"
    query_ids = {
        task_key: upsert_query(w, query_name(task_key),
                               (SQL_DIR / filename).read_text(), parent_path, with_param)
        for task_key, filename, _, with_param in TASKS
    }
    settings = job_settings(query_ids)

    existing = next((job for job in w.jobs.list(name=JOB_NAME) if job.settings
                     and job.settings.name == JOB_NAME), None)
    if existing is None:
        job_id = w.jobs.create(**_typed(settings)).job_id
        action = "created"
    else:
        job_id = existing.job_id
        w.jobs.reset(job_id=job_id, new_settings=j.JobSettings.from_dict(settings))
        action = "updated"

    state = w.jobs.get(job_id=job_id)
    print(json.dumps({
        "job": JOB_NAME, "job_id": job_id, "action": action,
        "schedule": state.settings.schedule.as_dict(),
        "tasks": [{"task_key": t.task_key,
                   "depends_on": [d.task_key for d in (t.depends_on or [])],
                   "max_retries": t.max_retries,
                   "min_retry_interval_millis": t.min_retry_interval_millis}
                  for t in state.settings.tasks],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
