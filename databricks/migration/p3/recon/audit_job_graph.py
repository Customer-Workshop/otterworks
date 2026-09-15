"""Read the deployed pipeline-3 jobs back from the Jobs API and assert the orchestration rules.

Evidence for the wave-3 orchestration unit, which moves no data and so has no recon run.
The rules are the ones pipeline 2 paid for:

  * every schedule PAUSED and in UTC, so deploying can never start anything on a timer
    and the cron text means the hour it reads;
  * max_concurrent_runs 1 with queueing, so a late run waits instead of racing;
  * every working task on the serverless environment, stated positively - the absence
    of cluster fields is not proof of serverless, so the environment key is required
    and the task kind must be one this pipeline actually uses;
  * the whole retry policy on the tasks that do the work, and none of it on a
    run_job_task, because Databricks drops task-level retry policy there;
  * no two jobs starting the same pipeline. Pipeline 3 defines no pipelines, so this
    is checked as "no pipeline_task at all" rather than assumed;
  * the task graph itself, against the expected keys and edges below, because rules
    applied per deployed task are satisfied vacuously by a job that lost one;
  * the byte-gate condition each export job is gated on, stated as the comparison it
    deploys with, so the gate cannot quietly widen to "always skip".

Usage:
    python3 databricks/migration/p3/recon/audit_job_graph.py [--json out.json]

Exits non-zero if any rule is violated.
"""
import argparse
import json
import sys

from databricks.sdk import WorkspaceClient

TIMEZONE = "UTC"
ENVIRONMENT_KEY = "serverless"
RETRY_INTERVAL_MILLIS = 300000
WORK_KINDS = {"spark_python_task", "sql_task"}

# Gate tasks: task key -> the comparison it must deploy with. A condition task carries no
# environment or retry policy, so those rules do not apply to it; what must hold is that
# the byte comparison downstream of it runs exactly when the frozen legacy objects cover
# the run date.
CONDITIONS = {
    "legacy_objects_cover_run_date":
        "{{job.parameters.run_date}} EQUAL_TO {{job.parameters.legacy_objects_run_date}}",
}

# The graph each job must deploy with: task key -> the tasks it waits for. A string
# value instead of a list means the task is a run_job_task running that job.
EXPECTED = {
    "ow_tp_p3_analytics_daily": {
        "cron": "0 0 2 * * ?",
        "tasks": {
            "land_events": [],
            "create_tables": ["land_events"],
            "load_silver": ["create_tables"],
            "load_gold_summary": ["load_silver"],
            "load_gold_hourly": ["load_silver"],
            "load_gold_top_users": ["load_silver"],
            "load_gold_top_user_actions": ["load_gold_top_users"],
            "publish_summary": ["load_gold_summary"],
            # P3-Q3: the legacy report objects, rebuilt from gold and byte-compared.
            "export_report_objects": ["load_gold_hourly", "load_gold_summary",
                                      "load_gold_top_user_actions", "load_gold_top_users"],
            "legacy_objects_cover_run_date": ["export_report_objects"],
            "compare_report_objects": ["legacy_objects_cover_run_date:true"],
        },
    },
    "ow_tp_p3_storage_cleanup_daily": {
        "cron": "0 30 2 * * ?",
        "tasks": {
            "land_inventory": [],
            "create_tables": ["land_inventory"],
            "compute_candidates": ["create_tables"],
            "report_candidates": ["compute_candidates"],
        },
    },
    "ow_tp_p3_audit_archive_weekly": {
        "cron": "0 0 3 ? * SUN",
        "tasks": {
            "land_audit_events": [],
            "create_tables": ["land_audit_events"],
            "archive_events": ["create_tables"],
            "write_compliance_report": ["archive_events"],
            "report_run": ["write_compliance_report"],
            # P3-Q3: the legacy archive and compliance objects, rebuilt from the governed
            # tables and byte-compared against the legacy's own bytes.
            "export_archive_objects": ["archive_events", "write_compliance_report"],
            "legacy_objects_cover_run_date": ["export_archive_objects"],
            "compare_archive_objects": ["legacy_objects_cover_run_date:true"],
        },
    },
    "ow_tp_p3_usage_rollup_daily": {
        "cron": "0 0 2 * * ?",
        "tasks": {
            "land_usage_events": [],
            "create_tables": ["land_usage_events"],
            "load_gold_usage_rollup": ["create_tables"],
        },
    },
    "ow_tp_p3_user_activity_daily": {
        "cron": "0 0 5 * * ?",
        "tasks": {
            # An edge, not a time offset: running the owning job queues this behind it.
            "upstream_analytics_daily": "ow_tp_p3_analytics_daily",
            "create_tables": ["upstream_analytics_daily"],
            "load_report": ["create_tables"],
            "load_report_days": ["create_tables"],
            "load_user_summary": ["create_tables"],
            "load_user_actions": ["load_user_summary"],
        },
    },
}


def collect(w):
    """Return {bare job name: settings dict} for every deployed pipeline-3 job.

    Development-mode deploys prefix the resource name with "[dev <principal>] ", so the
    deployed name is matched on its suffix rather than compared for equality.
    """
    found = {}
    for listed in w.jobs.list():
        name = listed.settings.name or ""
        bare = next((b for b in EXPECTED if name.endswith(b)), None)
        if bare is None:
            continue
        s = w.jobs.get(listed.job_id).settings
        tasks = {}
        for t in s.tasks or []:
            tasks[t.task_key] = {
                "kind": (
                    "run_job_task" if t.run_job_task
                    else "pipeline_task" if t.pipeline_task
                    else "condition_task" if t.condition_task
                    else "spark_python_task" if t.spark_python_task
                    else "sql_task" if t.sql_task
                    else "spark_jar_task" if t.spark_jar_task
                    else "other"
                ),
                "depends_on": sorted(
                    f"{d.task_key}:{d.outcome}" if d.outcome else d.task_key
                    for d in (t.depends_on or [])),
                "condition": (
                    f"{t.condition_task.left} {t.condition_task.op.value} "
                    f"{t.condition_task.right}" if t.condition_task else None),
                "max_retries": t.max_retries,
                "min_retry_interval_millis": t.min_retry_interval_millis,
                "retry_on_timeout": t.retry_on_timeout,
                "new_cluster": bool(t.new_cluster),
                "existing_cluster_id": t.existing_cluster_id,
                "environment_key": t.environment_key,
                "target_job_id": t.run_job_task.job_id if t.run_job_task else None,
                "pipeline_id": t.pipeline_task.pipeline_id if t.pipeline_task else None,
            }
        found[bare] = {
            "deployed_name": name,
            "job_id": listed.job_id,
            "cron": s.schedule.quartz_cron_expression if s.schedule else None,
            "timezone_id": s.schedule.timezone_id if s.schedule else None,
            "pause_status": s.schedule.pause_status.value if s.schedule else None,
            "max_concurrent_runs": s.max_concurrent_runs,
            "queue": bool(s.queue and s.queue.enabled),
            "timeout_seconds": s.timeout_seconds,
            "job_clusters": len(s.job_clusters or []),
            "tasks": tasks,
        }
    return found


def check(found):
    problems = []
    ids = {j["job_id"]: n for n, j in found.items()}

    for name, spec in EXPECTED.items():
        job = found.get(name)
        if job is None:
            problems.append(f"{name}: not deployed")
            continue
        if job["cron"] != spec["cron"]:
            problems.append(f"{name}: cron is {job['cron']}, expected {spec['cron']}")
        if job["timezone_id"] != TIMEZONE:
            problems.append(
                f"{name}: schedule timezone is {job['timezone_id']}, expected {TIMEZONE}; "
                "the same cron fires at a different instant"
            )
        if job["pause_status"] != "PAUSED":
            problems.append(f"{name}: schedule is {job['pause_status']}, expected PAUSED")
        if job["max_concurrent_runs"] != 1:
            problems.append(f"{name}: max_concurrent_runs is {job['max_concurrent_runs']}")
        if not job["queue"]:
            problems.append(f"{name}: queueing is off")
        if job["job_clusters"]:
            problems.append(f"{name}: defines {job['job_clusters']} job cluster(s)")

        missing = sorted(set(spec["tasks"]) - set(job["tasks"]))
        extra = sorted(set(job["tasks"]) - set(spec["tasks"]))
        if missing:
            problems.append(f"{name}: missing task(s) {missing}")
        if extra:
            problems.append(f"{name}: undeclared task(s) {extra}")

        for key, expected_deps in spec["tasks"].items():
            t = job["tasks"].get(key)
            if t is None:
                continue
            where = f"{name}.{key}"
            runs_job = isinstance(expected_deps, str)

            if t["depends_on"] != sorted([] if runs_job else expected_deps):
                problems.append(
                    f"{where}: depends_on is {t['depends_on']}, "
                    f"expected {sorted([] if runs_job else expected_deps)}"
                )
            if t["new_cluster"] or t["existing_cluster_id"]:
                problems.append(f"{where}: runs on a cluster, not serverless")
            if t["pipeline_id"]:
                problems.append(f"{where}: starts a pipeline; pipeline 3 defines none")

            if key in CONDITIONS:
                if t["kind"] != "condition_task":
                    problems.append(f"{where}: is a {t['kind']}, expected a condition_task")
                elif t["condition"] != CONDITIONS[key]:
                    problems.append(
                        f"{where}: gates on {t['condition']}, expected {CONDITIONS[key]}")
                continue

            if runs_job:
                if t["kind"] != "run_job_task":
                    problems.append(f"{where}: is a {t['kind']}, expected a run_job_task")
                elif ids.get(t["target_job_id"]) != expected_deps:
                    problems.append(
                        f"{where}: runs job {t['target_job_id']} "
                        f"({ids.get(t['target_job_id'], 'not a pipeline-3 job')}), "
                        f"expected {expected_deps}"
                    )
                asserted = [
                    f"{f}={t[f]}"
                    for f in ("max_retries", "min_retry_interval_millis", "retry_on_timeout")
                    if t[f]
                ]
                if asserted:
                    problems.append(
                        f"{where}: asserts {', '.join(asserted)} on a run_job_task, "
                        "which Databricks drops - put retries on the owning job's tasks"
                    )
                continue

            if t["kind"] not in WORK_KINDS:
                problems.append(f"{where}: task kind {t['kind']} is not one this pipeline uses")
            if t["environment_key"] != ENVIRONMENT_KEY:
                problems.append(
                    f"{where}: environment_key is {t['environment_key']}, "
                    f"expected {ENVIRONMENT_KEY}"
                )
            if t["max_retries"] != 2:
                problems.append(f"{where}: max_retries is {t['max_retries']}, expected 2")
            if t["min_retry_interval_millis"] != RETRY_INTERVAL_MILLIS:
                problems.append(
                    f"{where}: min_retry_interval_millis is "
                    f"{t['min_retry_interval_millis']}, expected {RETRY_INTERVAL_MILLIS}"
                )
            if not t["retry_on_timeout"]:
                problems.append(f"{where}: retry_on_timeout is off")

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the collected job graph here")
    args = ap.parse_args()

    found = collect(WorkspaceClient())
    problems = check(found)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(found, fh, indent=2, sort_keys=True)

    for name in EXPECTED:
        job = found.get(name)
        if job is None:
            continue
        edges = [
            f"{k} -> job {t['target_job_id']}"
            for k, t in job["tasks"].items()
            if t["kind"] == "run_job_task"
        ]
        print(
            f"{name}: {job['cron']} {job['timezone_id']} {job['pause_status']} "
            f"conc={job['max_concurrent_runs']} queue={job['queue']} "
            f"clusters={job['job_clusters']} tasks={len(job['tasks'])}"
            + (f" edges={edges}" if edges else "")
        )

    if problems:
        print("\nFAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        "\nOK: graph as declared, schedules paused in UTC, serverless only, "
        "full retry policy on owning tasks, no pipeline starts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
