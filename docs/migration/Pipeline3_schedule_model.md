# Pipeline 3 — orchestration: the five converted schedules and the edges between them

Status: **built and deployed PAUSED** (wave 3). This document applies pipeline 2's model
(`docs/migration/Pipeline2_schedule_model.md`) to pipeline 3's own jobs; it does not invent a
second model. Conversion table, timezone (P2-D04), `max_concurrent_runs: 1`, the retry block
and PAUSED-until-cutover all come from there.

Everything below was read back from the workspace with the Jobs API after
`databricks bundle deploy -t migration`, not transcribed from the YAML.

## 1. Legacy schedules → jobs

`etl/crontab` (five Python jobs) plus one Helm CronJob in the analytics service.

| Legacy schedule | Where it lives | Quartz | Job |
|---|---|---|---|
| `0 2 * * *` | `etl/crontab` | `0 0 2 * * ?` | `ow_tp_p3_analytics_daily` |
| `30 2 * * *` | `etl/crontab` | `0 30 2 * * ?` | `ow_tp_p3_storage_cleanup_daily` |
| `0 3 * * 0` | `etl/crontab` | `0 0 3 ? * SUN` | `ow_tp_p3_audit_archive_weekly` |
| `0 4 * * 0` | `etl/crontab` | — | **none** — `search_reindex_weekly.py` is out of Databricks scope (P3-D05) |
| `0 5 * * *` | `etl/crontab` | `0 0 5 * * ?` | `ow_tp_p3_user_activity_daily` |
| `0 2 * * *` | analytics-service Helm CronJob | `0 0 2 * * ?` | `ow_tp_p3_usage_rollup_daily` |

The Scala rollup's schedule was the one that did not exist in `etl/crontab` at all; it is a
Kubernetes CronJob, which is why the census first read it as unscheduled. It is nightly 02:00
UTC and writes to an `emptyDir` that dies with the pod (F-0.6) — migrated per P3-D07, with
"should this run at all" carried to STOP E.

`search_reindex_weekly.py` has no job and no schedule here on purpose. A placeholder would be
a job nobody can reconcile; the gap is declared instead.

## 2. Timing replaced by a dependency

The only real cross-job edge in pipeline 3 is `user_activity_daily` → `analytics_daily`. In
the legacy that edge is a **three-hour guess**: analytics writes at 02:00, user-activity reads
at 05:00 and simply hopes the summary row and the top-user files are there. They are not
always: the legacy skips a missing day silently, so a late or failed 02:00 run shows up as a
quietly shorter report rather than an error.

The converted job does not reproduce the guess:

```
ow_tp_p3_user_activity_daily   (PAUSED, 0 0 5 * * ?)
  upstream_analytics_daily     run_job_task -> ow_tp_p3_analytics_daily
  create_tables                depends_on: upstream_analytics_daily
  load_report                  depends_on: create_tables
  load_report_days             depends_on: create_tables
  load_user_summary            depends_on: create_tables
  load_user_actions            depends_on: load_user_summary
```

**Why `run_job_task` and not a shared pipeline or a duplicated task.** Pipeline 2 learned this
the expensive way: two jobs that start the same pipeline collide, because a pipeline permits
one active update and job-level queueing is per job. A dependent job therefore reaches another
job's output by running *the owning job*, so it queues behind whatever the owner is already
doing. Pipeline 3 has no Lakeflow pipelines at all, but the same rule decides the shape here:
user-activity does not re-implement the analytics loads, it runs the analytics job.

**Retries are not set on the `run_job_task`.** Databricks drops task-level retry policy on a
`run_job_task`, so a value there would be a claim the platform silently discards. The retries
live on `ow_tp_p3_analytics_daily`'s own tasks, which is where the work — and the transient
failure — actually happens.

**Re-running the owner is safe.** Every analytics task is a full recompute of one `run_date`
partition written with `INSERT ... REPLACE WHERE`, so the 05:00 invocation either finds the
02:00 run's output already correct and rewrites identical bytes, or produces it. That is the
same property the idempotency reruns prove per unit.

One consequence worth stating plainly: with the schedules activated, the analytics job would
run twice a day — its own 02:00 trigger and the 05:00 dependency — where the legacy ran it
once. The output is unchanged; the compute is not free. If that is unwanted at cutover, the
answer is to drop the analytics job's own schedule and let user-activity drive it, not to go
back to a time offset.

The other four jobs share no output table and read nothing of each other's, which is why they
ran as independent units and carry no edges.

## 3. Settings, inherited wholesale from pipeline 2

| Setting | Value | Applies to |
|---|---|---|
| `pause_status` | `PAUSED` | every schedule, plus the target's `trigger_pause_status` preset |
| `max_concurrent_runs` | 1 | all five jobs |
| `queue.enabled` | true | all five jobs — a late run waits instead of being dropped |
| `timeout_seconds` | 3600 | all five jobs |
| `max_retries` | 2 | every task that does work; never on the `run_job_task` |
| `min_retry_interval_millis` | 300000 | same |
| `retry_on_timeout` | true | same |
| `webhook_notifications.on_failure` | `${var.failure_webhooks}`, empty in `migration` | all five jobs |
| compute | serverless `environment_key` only | every task |

No `job_clusters`, no `new_cluster`, no `existing_cluster_id`, no `spark_jar_task` anywhere in
the bundle — including for the Scala rollup, which became SQL on Delta (P3-D06). The bundle
has exactly one target, `migration`; there is no production target to deploy by accident.

## 4. Deployed state, read back from the API

| Job | Cron | Pause | Conc | Queue | Clusters | Tasks | Tasks with retries |
|---|---|---|---:|---|---:|---:|---:|
| `ow_tp_p3_analytics_daily` | `0 0 2 * * ?` | PAUSED | 1 | yes | 0 | 8 | 8 |
| `ow_tp_p3_storage_cleanup_daily` | `0 30 2 * * ?` | PAUSED | 1 | yes | 0 | 4 | 4 |
| `ow_tp_p3_audit_archive_weekly` | `0 0 3 ? * SUN` | PAUSED | 1 | yes | 0 | 5 | 5 |
| `ow_tp_p3_usage_rollup_daily` | `0 0 2 * * ?` | PAUSED | 1 | yes | 0 | 3 | 3 |
| `ow_tp_p3_user_activity_daily` | `0 0 5 * * ?` | PAUSED | 1 | yes | 0 | 6 | 5 + 1 `run_job_task` |

Every schedule is `timezone_id: UTC`, which matters as much as the expression: the same cron in
another zone fires at a different instant. The table is produced by
`databricks/migration/p3/recon/audit_job_graph.py`, which also compares the deployed task keys
and `depends_on` edges against the graph declared in the script, requires
`environment_key: serverless` and the full retry triple (`max_retries`,
`min_retry_interval_millis`, `retry_on_timeout`) on every working task, and rejects all three of
those on the `run_job_task`. Checking only the tasks the API returns would let a job that
deployed with tasks missing pass every rule vacuously.

The two 02:00 jobs (`analytics_daily` and `usage_rollup_daily`) no longer collide with anything:
they share no box, no table and no input, and the legacy 02:00/02:10 overlap with
`finance_excel_report.pl` disappeared with pipeline 2's conversion. The 02:30 cleanup job
likewise only overlapped analytics because both ran on the ETL box.

## 5. What is not proven here

- **The full two-job chain has never completed green.** The `run_job_task` edge is verified —
  the analytics job really is started and user-activity really does wait on it — but the
  analytics job's `publish_summary` task fails on the missing named secret
  `ow_tp/analytics_postgres_password`, so the run ends in failure and the downstream tasks
  are skipped. The user-activity tasks were run and reconciled directly instead. Provisioning
  that secret is a customer action (STOP E).
- **No schedule has ever fired.** Everything here was exercised by explicit runs. Activation
  is a cutover action for the customer's principal.
- **`source_principal_read_only` is unverified** for every pipeline-3 unit (P3-D09).
