"""Structural verification for the wave-4 orchestration unit.

    python3 databricks/migration/p2/recon/verify_job_structure.py

There is no row parity to compute here: the jobs move no data of their own, so the
evidence is the shape of what was deployed, read back from the workspace rather than
from the bundle file that produced it. Each check below is one thing `run_all.sh` or
the crontab did that the target must no longer do:

  - the two `sleep 600` calls become `depends_on` edges;
  - the parse's own `5-59/15` cron entry disappears (it is an edge, not a schedule);
  - `|| true` on every stage disappears (a failed task fails the run, then retries);
  - three `/tmp` lock files that never provided mutual exclusion become
    `max_concurrent_runs: 1`;
  - nothing runs on a timer from a migration session: every schedule is PAUSED;
  - no cluster is created: every task runs on serverless.

Jobs are matched by suffix because a development-mode bundle deploys them as
"[dev <principal>] <name>".
"""

from __future__ import annotations

import json
import sys

from databricks.sdk import WorkspaceClient

EXPECTED = {
    "ow_tp_p2_custbill_ingest": {
        "quartz": "0 0/15 * * * ?",
        "edges": {"land_files": [], "custbill_pipeline": ["land_files"]},
        "serverless_tasks": ["land_files"],
        "queue_enabled": True,
    },
    "ow_tp_p2_finance_close": {
        "quartz": "0 10 2 * * ?",
        "edges": {"await_silver": [], "export_csv_xls": ["await_silver"]},
        "serverless_tasks": ["export_csv_xls"],
        "queue_enabled": True,
        # The close reaches the pipeline through the ingest job, never directly: one
        # pipeline allows one active update, so two jobs starting it is a collision,
        # not an ordering.
        "runs_job": ("await_silver", "ow_tp_p2_custbill_ingest"),
        "no_pipeline_task": True,
    },
}
RETRY = {"max_retries": 2, "min_retry_interval_millis": 300000, "retry_on_timeout": True}


def _find(client: WorkspaceClient, name: str):
    matches = [j for j in client.jobs.list(expand_tasks=True) if str(j.settings.name).endswith(name)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one deployed job ending {name!r}, found {len(matches)}")
    return client.jobs.get(matches[0].job_id)


def check_job(client: WorkspaceClient, name: str, expected: dict) -> list[dict]:
    job = _find(client, name)
    s = job.settings
    tasks = {t.task_key: t for t in s.tasks}
    edges = {k: sorted(d.task_key for d in (t.depends_on or [])) for k, t in tasks.items()}
    out = [
        {"job": name, "check": "job_id", "value": str(job.job_id), "ok": True},
        {
            "job": name,
            "check": "schedule_quartz",
            "value": s.schedule and s.schedule.quartz_cron_expression,
            "ok": bool(s.schedule) and s.schedule.quartz_cron_expression == expected["quartz"],
        },
        {
            "job": name,
            "check": "schedule_paused",
            "value": s.schedule and str(s.schedule.pause_status),
            "ok": bool(s.schedule) and str(s.schedule.pause_status) == "PauseStatus.PAUSED",
        },
        {
            "job": name,
            "check": "task_graph",
            "value": edges,
            "ok": edges == {k: sorted(v) for k, v in expected["edges"].items()},
        },
        {
            "job": name,
            "check": "max_concurrent_runs_1",
            "value": s.max_concurrent_runs,
            "ok": s.max_concurrent_runs == 1,
        },
        {"job": name, "check": "timeout_seconds", "value": s.timeout_seconds, "ok": s.timeout_seconds == 3600},
        {
            "job": name,
            # A run_job_task cannot carry a retry policy: Databricks drops it, and the
            # tasks inside the job it runs carry their own.
            "check": "retry_policy_on_every_retryable_task",
            "value": {
                k: [t.max_retries, t.min_retry_interval_millis, t.retry_on_timeout] for k, t in tasks.items()
            },
            "ok": all(
                t.max_retries == RETRY["max_retries"]
                and t.min_retry_interval_millis == RETRY["min_retry_interval_millis"]
                and bool(t.retry_on_timeout) == RETRY["retry_on_timeout"]
                for t in tasks.values()
                if not t.run_job_task
            ),
        },
        {
            "job": name,
            "check": "no_cluster_created",
            "value": {k: [t.new_cluster, t.existing_cluster_id, t.job_cluster_key] for k, t in tasks.items()},
            "ok": all(
                t.new_cluster is None and t.existing_cluster_id is None and t.job_cluster_key is None
                for t in tasks.values()
            )
            and not s.job_clusters,
        },
        {
            "job": name,
            "check": "python_tasks_serverless",
            "value": {k: t.environment_key for k, t in tasks.items() if t.spark_python_task},
            "ok": all(tasks[k].environment_key for k in expected["serverless_tasks"]),
        },
        {
            "job": name,
            "check": "queue_enabled",
            "value": s.queue and s.queue.enabled,
            "ok": bool(s.queue and s.queue.enabled) == expected["queue_enabled"],
        },
        {
            "job": name,
            "check": "failure_notification_destination_empty_in_migration",
            "value": s.webhook_notifications and s.webhook_notifications.as_dict(),
            "ok": not (s.webhook_notifications and s.webhook_notifications.on_failure),
        },
    ]
    if expected.get("no_pipeline_task"):
        out.append(
            {
                "job": name,
                "check": "does_not_start_the_shared_pipeline_directly",
                "value": [k for k, t in tasks.items() if t.pipeline_task],
                "ok": not any(t.pipeline_task for t in tasks.values()),
            }
        )
    if expected.get("runs_job"):
        task_key, target_name = expected["runs_job"]
        target = _find(client, target_name)
        task = tasks.get(task_key)
        out.append(
            {
                "job": name,
                "check": f"{task_key}_runs_{target_name}",
                "value": task and task.run_job_task and str(task.run_job_task.job_id),
                "ok": bool(task and task.run_job_task and task.run_job_task.job_id == target.job_id),
            }
        )
    return out


def main() -> None:
    client = WorkspaceClient()
    results = []
    for name, expected in EXPECTED.items():
        results += check_job(client, name, expected)
    report = {
        "checks": results,
        "failed": [r for r in results if not r["ok"]],
        "verdict": "PASS" if all(r["ok"] for r in results) else "FAIL",
    }
    print(json.dumps(report, indent=2, default=str))
    if report["verdict"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
