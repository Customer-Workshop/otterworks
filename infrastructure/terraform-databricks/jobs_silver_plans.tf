# silver_plans: OW_BILLING pkg_plans (fn_list_plans, fn_entitlement, sp_change_plan) -> ow_tp.silver.*
#
# Serverless-only, ns-parameterised, MERGE-idempotent. max_concurrent_runs = 1 because the source's
# own close-out is order-dependent and because wave 4 (sp_suspend_overdue) also writes
# ow_tp.silver.subscriptions: this job merges only the identities its own run produces, keyed on the
# natural key plus ns, and issues no table-wide statement.

resource "databricks_notebook" "silver_plans" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_silver_plans.py"
  path     = "${var.notebook_root}/ow_tp_silver_plans"
  language = "PYTHON"
}

resource "databricks_workspace_file" "silver_plans_spec" {
  source = "${path.module}/../../databricks/ddl/silver_plans_spec.json"
  path   = "${var.notebook_root}/silver_plans_spec.json"
}

resource "databricks_job" "silver_plans" {
  name        = "ow_tp_silver_plans"
  description = "Silver plans port for plans, subscriptions, entitlements, and quarantine_silver_plans."

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
    name    = "entitlement_on"
    default = "2026-02-28"
  }

  parameter {
    name    = "change_effective_on"
    default = "2026-03-01"
  }

  # No secret is needed: this reads only ow_tp.bronze.* Unity Catalog tables and writes only this
  # unit's four ow_tp.silver.* targets, so there is no dbutils.secrets lookup or credential.
  task {
    task_key = "plans"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.silver_plans.path
      source        = "WORKSPACE"

      # The tier and status maps, the 2099 sentinel, and the close-out and tie-break orderings are
      # not job parameters. They are constants of the source package body with no column in the
      # source schema or in bronze, so they are pinned in the frozen spec and asserted at load time
      # rather than exposed as knobs the deployed job could change semantics with.
      base_parameters = {
        ns                  = "{{job.parameters.ns}}"
        catalog             = "{{job.parameters.catalog}}"
        schema              = "silver"
        bronze_schema       = "bronze"
        entitlement_on      = "{{job.parameters.entitlement_on}}"
        change_effective_on = "{{job.parameters.change_effective_on}}"
        spec_path           = databricks_workspace_file.silver_plans_spec.path
        landing_root        = var.landing_path
        batch_id            = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = "silver_plans"
    layer = "silver"
    owner = "ow_tp"
  }
}
