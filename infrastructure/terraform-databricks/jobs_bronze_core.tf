# bronze_core: OW_BILLING normalised core tables -> ow_tp.bronze.*
#
# Serverless notebook task only: no cluster, no warehouse, no other hourly-cost resource is
# declared here, and nothing in the shared stack is modified. The job takes ns as a parameter
# so a run only ever touches its own slice, and the notebook merges on the natural key plus ns,
# which is what makes a rerun a no-op.

resource "databricks_notebook" "bronze_core" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_bronze_core.py"
  path     = "${var.notebook_root}/ow_tp_bronze_core"
  language = "PYTHON"
}

# Column/type contract shared by the load and the recon, so the pinned Databricks types for
# unbounded Oracle NUMBER columns cannot drift between the two.
resource "databricks_workspace_file" "bronze_core_spec" {
  source = "${path.module}/../../databricks/ddl/bronze_core_spec.json"
  path   = "${var.notebook_root}/bronze_core_spec.json"
}

resource "databricks_job" "bronze_core" {
  name        = "ow_tp_bronze_core"
  description = "Bronze load of the OW_BILLING core billing tables (13 tables plus quarantine_bronze_core)."

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
    name    = "landing_root"
    default = var.landing_path
  }

  task {
    task_key = "load"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.bronze_core.path
      source        = "WORKSPACE"

      base_parameters = {
        ns           = "{{job.parameters.ns}}"
        catalog      = "{{job.parameters.catalog}}"
        schema       = "bronze"
        landing_root = "{{job.parameters.landing_root}}"
        spec_path    = databricks_workspace_file.bronze_core_spec.path
        batch_id     = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = "bronze_core"
    layer = "bronze"
    owner = "ow_tp"
  }
}
