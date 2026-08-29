# silver_rating: OW_BILLING rating engine -> ow_tp.silver.*
#
# Serverless-only, ns-parameterised, and MERGE-idempotent: reruns merge on the natural key plus
# ns so a run only ever touches its own slice.

resource "databricks_notebook" "silver_rating" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_silver_rating.py"
  path     = "${var.notebook_root}/ow_tp_silver_rating"
  language = "PYTHON"
}

resource "databricks_workspace_file" "silver_rating_spec" {
  source = "${path.module}/../../databricks/ddl/silver_rating_spec.json"
  path   = "${var.notebook_root}/silver_rating_spec.json"
}

resource "databricks_job" "silver_rating" {
  name        = "ow_tp_silver_rating"
  description = "Silver rating engine port for rating_periods, rating_results, and quarantine_silver_rating."

  max_concurrent_runs = 1

  parameter {
    name    = "ns"
    default = var.ns
  }

  parameter {
    name    = "catalog"
    default = var.catalog
  }

  parameter {
    name    = "period_start"
    default = "2026-02-01"
  }

  parameter {
    name    = "period_end"
    default = "2026-02-28"
  }

  # No secret is needed: this reads only ow_tp.bronze.* Unity Catalog tables and writes only
  # this unit's three ow_tp.silver.* targets, so there is no dbutils.secrets lookup or credential.
  task {
    task_key = "rate"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.silver_rating.path
      source        = "WORKSPACE"

      # The notebook's plan_overrides widget is deliberately not wired to a job parameter: the
      # deployed job rates money only from what bronze carries. It defaults to empty and is passed
      # per run by the re-rate proof.
      base_parameters = {
        ns           = "{{job.parameters.ns}}"
        catalog      = "{{job.parameters.catalog}}"
        schema       = "silver"
        period_start = "{{job.parameters.period_start}}"
        period_end   = "{{job.parameters.period_end}}"
        spec_path    = databricks_workspace_file.silver_rating_spec.path
        landing_root = var.landing_path
        batch_id     = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = "silver_rating"
    layer = "silver"
    owner = "ow_tp"
  }
}
