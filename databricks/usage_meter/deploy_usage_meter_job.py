"""Create or update the `ow_tp_usage_meter` Lakeflow Job. Schedule stays PAUSED.

Four serverless tasks in a line -- land, normalise, meter, publish -- each
retried twice, so a transient warehouse or Lakebase hiccup does not need a human.
No cluster is created: serverless tasks carry their own compute, and the Lakebase
publish task gets `psycopg` from its task environment.

The job runs the same files that live in this directory; they are uploaded to the
workspace first so the job does not depend on a checkout.

    python3 deploy_usage_meter_job.py [--run]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import timedelta
from pathlib import Path

JOB_NAME = "ow_tp_usage_meter"
# 04:15 UTC daily, after the nightly billing batch. Paused until a human enables it.
CRON = "0 15 4 * * ?"
TIMEZONE = "UTC"
LAKEBASE_BRANCH = "mig-p1-w0"
SOURCE = Path(__file__).resolve().parent
FILES = ("executor.py", "meter_sql.py", "pipeline.py", "landing.py", "lakebase_sync.py")


def upload(w, root: str) -> None:
    from databricks.sdk.service.workspace import ImportFormat

    w.workspace.mkdirs(root)
    for name in FILES:
        w.workspace.upload(f"{root}/{name}", io.BytesIO((SOURCE / name).read_bytes()),
                           format=ImportFormat.AUTO, overwrite=True)


def settings(root: str) -> dict:
    def task(key: str, script: str, params: list[str], depends: str | None) -> dict:
        spec = {
            "task_key": key,
            "spark_python_task": {"python_file": f"/Workspace{root}/{script}",
                                  "source": "WORKSPACE", "parameters": params},
            "environment_key": "meter",
            "max_retries": 2,
            "min_retry_interval_millis": 60_000,
            "retry_on_timeout": True,
            "timeout_seconds": 3600,
        }
        if depends:
            spec["depends_on"] = [{"task_key": depends}]
        return spec

    return {
        "name": JOB_NAME,
        "description": ("Per-tenant usage meter: lands usage events in ow_tp.bronze, normalises "
                        "and dedupes into ow_tp.silver, meters per tenant/metric/month in "
                        "ow_tp.gold, and publishes the current period to Lakebase "
                        f"({LAKEBASE_BRANCH}, schema billing) for the billing application."),
        "tasks": [
            task("land_usage_events", "pipeline.py", ["ingest"], None),
            task("normalise_usage_events", "pipeline.py", ["normalise"], "land_usage_events"),
            task("meter_usage", "pipeline.py", ["meter"], "normalise_usage_events"),
            task("publish_to_lakebase", "lakebase_sync.py", ["--branch", LAKEBASE_BRANCH],
                 "meter_usage"),
        ],
        "environments": [{"environment_key": "meter",
                          "spec": {"client": "3", "dependencies": ["psycopg[binary]"]}}],
        "schedule": {"quartz_cron_expression": CRON, "timezone_id": TIMEZONE,
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
        "queue": {"enabled": True},
        "tags": {"ow_tp": "usage-meter"},
    }


def deploy(run: bool = False) -> dict:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service import jobs as j

    w = WorkspaceClient()
    root = f"/Users/{w.current_user.me().user_name}/{JOB_NAME}"
    upload(w, root)

    spec = j.JobSettings.from_dict(settings(root))
    existing = next((job for job in w.jobs.list(name=JOB_NAME)), None)
    if existing:
        w.jobs.reset(job_id=existing.job_id, new_settings=spec)
        job_id = existing.job_id
    else:
        job_id = w.jobs.create(name=spec.name, description=spec.description, tasks=spec.tasks,
                               environments=spec.environments, schedule=spec.schedule,
                               max_concurrent_runs=spec.max_concurrent_runs, queue=spec.queue,
                               tags=spec.tags).job_id

    out = {"job_id": job_id, "name": JOB_NAME, "pause_status": "PAUSED", "workspace_path": root}
    if run:
        result = w.jobs.run_now(job_id=job_id).result(timeout=timedelta(minutes=45))
        out["run_id"] = result.run_id
        out["result_state"] = str(result.state.result_state)
        out["tasks"] = {t.task_key: str(t.state.result_state) for t in result.tasks}
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="trigger one run after deploying")
    args = parser.parse_args(argv)
    print(json.dumps(deploy(args.run), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
