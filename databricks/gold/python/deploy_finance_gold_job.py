#!/usr/bin/env python3
"""Deploy the Lakeflow job `ow_tp_finance_gold`: refresh the gold tables, PAUSED.

    python3 databricks/gold/python/deploy_finance_gold_job.py [--dry-run]

One SQL task per gold table, wired in dependency order, all on the existing serverless
warehouse (no cluster is created). Each task's body is a Databricks SQL query object
rewritten from the repo file on every deploy, so what runs in the workspace is always the
text in `databricks/gold/sql/`.

Shape of the graph:

    build_subscription_mrr ─┬─> build_usage_period ──> build_storage_cost ─┬─> build_dq_exceptions
    build_ar_open_invoice ──┴───────────────────────────────────────────────┘

`build_dq_exceptions` runs last because it reads the tables the other tasks write; it is the
record of what each metric did with dirty source rows, so a refresh that skipped it would
publish numbers with no audit trail.

Retries: 2 attempts after a failure, 5 minutes apart, on every task. These statements are
CREATE OR REPLACE and read only committed Delta snapshots, so a retry recomputes from
scratch and cannot double-count; the failure mode worth retrying is a transient warehouse or
metastore error.

The schedule (06:15 UTC daily, after the nightly billing batch) is created PAUSED and stays
paused until someone turns it on deliberately.

Two job parameters, both defaulting to empty, which each statement reads as "derive it":
`as_of_ts` prices ARR/MRR at the moment of the run, and `as_of_date` ages AR at the latest
invoice date in the ledger. A backdated rebuild is a parameter on a run, not an edit.

Not in this job: the Lakebase reference ingestion
(`databricks/gold/python/ingest_lakebase_reference.py`). It needs Python compute to reach
Postgres, and no new clusters may be created here, so it is run deliberately rather than on
a schedule. The tables it loads (plans, tenants, subscriptions, credit notes, rating
results) change rarely; the ones this job rebuilds are the ones that move. The staleness
window that leaves is not silent: `build_dq_exceptions` raises `reference_snapshot_stale`
once a reference snapshot is more than 7 days old, so a scheduled refresh that prices ARR
from an old snapshot says so on the dashboard.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as j
from databricks.sdk.service import sql as sqlsvc

JOB_NAME = "ow_tp_finance_gold"
WAREHOUSE = "565cd2fd713738c4"
CRON = "0 15 6 * * ?"
TIMEZONE = "UTC"
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

# task_key -> (sql file, dependencies)
TASKS: list[tuple[str, str, list[str]]] = [
    ("build_subscription_mrr", "10_fct_subscription_mrr.sql", []),
    ("build_ar_open_invoice", "20_fct_ar_open_invoice.sql", []),
    ("build_usage_period", "30_fct_usage_period.sql", ["build_subscription_mrr"]),
    ("build_storage_cost", "40_fct_storage_cost_tenant.sql", ["build_usage_period"]),
    ("build_dq_exceptions", "50_dq_exceptions.sql",
     ["build_ar_open_invoice", "build_storage_cost"]),
]
PARAMETERS = {"as_of_ts": "", "as_of_date": ""}


def upsert_query(w: WorkspaceClient, name: str, text: str, parent_path: str,
                 parameters: list[str]) -> str:
    # A display name is not an identity: match on the folder too, and refuse to guess when
    # more than one query matches.
    named = [w.queries.get(id=q.id) for q in w.queries.list(page_size=100)
             if q.display_name == name]
    matches = [q for q in named
               if (q.parent_path or "").removeprefix("/Workspace") == parent_path]
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} queries named {name} under {parent_path}: "
                         "refusing to pick one")
    params = [sqlsvc.QueryParameter(name=p, title=p,
                                    text_value=sqlsvc.TextValue(value=""))
              for p in parameters]
    if not matches:
        return w.queries.create(query=sqlsvc.CreateQueryRequestQuery(
            display_name=name, query_text=text, warehouse_id=WAREHOUSE,
            parent_path=parent_path, parameters=params,
            description="ow_tp finance gold layer: deployed from databricks/gold/sql")).id
    existing = matches[0]
    w.queries.update(id=existing.id, update_mask="query_text,warehouse_id,parameters",
                     query=sqlsvc.UpdateQueryRequestQuery(
                         query_text=text, warehouse_id=WAREHOUSE, parameters=params))
    return existing.id


def job_settings(query_ids: dict[str, str]) -> dict:
    tasks = []
    for task_key, filename, depends in TASKS:
        text = (SQL_DIR / filename).read_text()
        task_params = {p: "{{job.parameters.%s}}" % p for p in PARAMETERS if f":{p}" in text}
        tasks.append({
            "task_key": task_key,
            "depends_on": [{"task_key": d} for d in depends],
            "max_retries": 2,
            "min_retry_interval_millis": 300000,
            "retry_on_timeout": True,
            "timeout_seconds": 3600,
            "sql_task": {
                "query": {"query_id": query_ids[task_key]},
                "warehouse_id": WAREHOUSE,
                **({"parameters": task_params} if task_params else {}),
            },
        })
    return {
        "name": JOB_NAME,
        "description": ("Refresh the ow_tp finance gold tables (ARR/MRR, AR ageing, "
                        "overage, storage cost, data-quality exceptions) on the existing "
                        "serverless warehouse. Schedule created PAUSED."),
        "parameters": [{"name": k, "default": v} for k, v in PARAMETERS.items()],
        "tasks": tasks,
        "schedule": {"quartz_cron_expression": CRON, "timezone_id": TIMEZONE,
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
        "queue": {"enabled": True},
    }


def _typed(settings: dict) -> dict:
    parsed = j.JobSettings.from_dict(settings)
    return {"name": parsed.name, "description": parsed.description,
            "parameters": parsed.parameters, "tasks": parsed.tasks,
            "schedule": parsed.schedule, "queue": parsed.queue,
            "max_concurrent_runs": parsed.max_concurrent_runs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.dry_run:
        print(json.dumps(job_settings({t[0]: "<query_id>" for t in TASKS}), indent=2))
        return 0

    w = WorkspaceClient()
    parent_path = f"/Users/{w.current_user.me().user_name}"
    query_ids = {}
    for task_key, filename, _ in TASKS:
        text = (SQL_DIR / filename).read_text()
        query_ids[task_key] = upsert_query(
            w, f"{JOB_NAME}__{task_key}", text, parent_path,
            [p for p in PARAMETERS if f":{p}" in text])

    settings = job_settings(query_ids)
    existing = next((job for job in w.jobs.list(name=JOB_NAME)
                     if job.settings and job.settings.name == JOB_NAME), None)
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
                   "max_retries": t.max_retries}
                  for t in state.settings.tasks],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
