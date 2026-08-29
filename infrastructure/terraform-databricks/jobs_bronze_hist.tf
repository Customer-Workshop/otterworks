# bronze_hist — CUSTOMER_MASTER_HIST and SUBSCRIPTIONS_HIST.
#
# In the billing estate these tables are filled by row-level capture triggers on
# every update and delete. Those triggers are retired on the target: the existing
# rows migrate as first-class tables and change history from cutover forward is
# Delta history, so this job loads, it does not capture.
#
# The load is a batch over the whole history rather than a recent window, and it
# is restartable: the notebook merges on the namespace plus a deterministic key,
# so a repeated run over identical input writes nothing.

resource "databricks_job" "bronze_hist" {
  name                = "ow_tp_bronze_hist"
  description         = "Migrate the legacy CUSTOMER_MASTER_HIST and SUBSCRIPTIONS_HIST tables into ow_tp.bronze, with HIST_DT parsed and rejects accounted for in quarantine_bronze_hist."
  max_concurrent_runs = 1
  timeout_seconds     = 3600

  # The namespace is a run parameter, not a property of the job: one definition
  # serves every namespace and nothing is baked into the job name.
  parameter {
    name    = "ns"
    default = var.ns
  }

  parameter {
    name    = "catalog"
    default = var.catalog
  }

  parameter {
    name    = "landing_root"
    default = var.landing_path
  }

  # Cutover sequencing is the orchestrator's decision, not a wall clock's. The
  # schedule exists so the shape is reviewable, and stays paused until then.
  schedule {
    quartz_cron_expression = "0 30 2 * * ?"
    timezone_id            = "UTC"
    pause_status           = "PAUSED"
  }

  task {
    task_key = "load_hist"

    # A notebook task with no cluster block runs on serverless job compute. No
    # cluster, no warehouse, nothing with an hourly floor is created here.
    notebook_task {
      notebook_path = "${var.notebook_root}/bronze_hist_load"
      base_parameters = {
        ns           = "{{job.parameters.ns}}"
        catalog      = "{{job.parameters.catalog}}"
        landing_root = "{{job.parameters.landing_root}}"
      }
    }
  }

  tags = {
    demo     = "tech-partnerships"
    pipeline = "bronze_hist"
    layer    = "bronze"
  }
}
