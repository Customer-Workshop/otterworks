# silver_dunning: OW_BILLING pkg_dunning (fn_overdue_accounts, sp_schedule_dunning,
# sp_suspend_overdue) and JOB_NIGHTLY_DUNNING -> ow_tp.silver.*
#
# JOB_NIGHTLY_DUNNING is one job action calling sp_schedule_dunning then sp_suspend_overdue over one
# state of the overdue population, so this is one job with two ordered tasks in one run rather than
# two scheduled jobs: the schedule task persists the overdue snapshot under
# <landing>/<ns>/silver_dunning/snapshots/{{job.run_id}}/ and the sweep task reads that file instead
# of re-querying ow_tp.silver.invoices, which is what keeps both entrypoints on one population
# (ACC-TWO-ENTRYPOINTS). Both tasks receive the same batch_id = {{job.run_id}}, which is how the
# second finds the first's snapshot.
#
# max_concurrent_runs = 1 because the source assigns attempt_no from an unlocked
# SELECT NVL(MAX(attempt_no),0)+1 per invoice: two overlapping runs would collide on
# uq_dunning_attempts, which the source's WHEN OTHERS THEN NULL would hide and this unit will not.
#
# This job writes ow_tp.silver.dunning_attempts, ow_tp.silver.notifications, ow_tp.silver.tenants and
# ow_tp.silver.quarantine_silver_dunning, and updates only status_cd and suspended_on on rows of
# ow_tp.silver.subscriptions that already exist in its own ns (D-30, matched-only MERGE, no INSERT,
# no DELETE, no DDL). ow_tp.silver.invoices and ow_tp.bronze.* are read-only to it, and
# ow_tp.bronze.tenants is never written.

resource "databricks_notebook" "silver_dunning" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_silver_dunning.py"
  path     = "${var.notebook_root}/ow_tp_silver_dunning"
  language = "PYTHON"
}

resource "databricks_workspace_file" "silver_dunning_spec" {
  source = "${path.module}/../../databricks/ddl/silver_dunning_spec.json"
  path   = "${var.notebook_root}/silver_dunning_spec.json"
}

resource "databricks_job" "silver_dunning" {
  name        = "ow_tp_silver_dunning"
  description = "Silver dunning port: scheduled attempts, the 14-day suspension sweep, suspension notifications, tenant status, and quarantine_silver_dunning."

  max_concurrent_runs = 1

  parameter {
    name    = "ns"
    default = var.ns
  }

  parameter {
    name    = "catalog"
    default = var.catalog
  }

  # The source's p_as_of is TRUNC(SYSDATE) in the scheduler. It is a parameter here so a run is
  # reproducible and so the recon report can pin the night it reconciles; both tasks of a run share
  # the one value, because a sweep on a different p_as_of than its schedule is a different night.
  parameter {
    name    = "as_of"
    default = "2026-02-28"
  }

  # 'silver' is ow_tp.silver.invoices, silver_invoicing's target and this unit's read-only overdue
  # population. 'bronze' exists only for a declared generated-fixture namespace, whose invoices
  # cannot be seeded into another unit's silver target.
  parameter {
    name    = "invoice_source"
    default = "silver"
  }

  # No secret is needed: the tasks read ow_tp Unity Catalog tables and write this unit's ow_tp.silver
  # targets, so there is no dbutils.secrets lookup and no credential in the job definition.
  task {
    task_key = "schedule_dunning"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.silver_dunning.path
      source        = "WORKSPACE"

      # The status and kind maps, the SAT/SUN shifts, the English day abbreviations, the 14-day cut
      # and the 'YYYYMMDD' comparison are constants of the source package body with no column in the
      # source schema, so they are pinned in the frozen spec and asserted at load time rather than
      # exposed as knobs a deployed job could change semantics with.
      base_parameters = {
        ns             = "{{job.parameters.ns}}"
        catalog        = "{{job.parameters.catalog}}"
        schema         = "silver"
        bronze_schema  = "bronze"
        as_of          = "{{job.parameters.as_of}}"
        invoice_source = "{{job.parameters.invoice_source}}"
        phase          = "schedule"
        spec_path      = databricks_workspace_file.silver_dunning_spec.path
        landing_root   = var.landing_path
        batch_id       = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  task {
    task_key = "suspend_overdue"

    # The source calls sp_suspend_overdue after sp_schedule_dunning inside one job action, and the
    # sweep reads the snapshot the schedule task wrote under this run's batch_id.
    depends_on {
      task_key = "schedule_dunning"
    }

    notebook_task {
      notebook_path = databricks_notebook.silver_dunning.path
      source        = "WORKSPACE"

      base_parameters = {
        ns             = "{{job.parameters.ns}}"
        catalog        = "{{job.parameters.catalog}}"
        schema         = "silver"
        bronze_schema  = "bronze"
        as_of          = "{{job.parameters.as_of}}"
        invoice_source = "{{job.parameters.invoice_source}}"
        phase          = "suspend"
        spec_path      = databricks_workspace_file.silver_dunning_spec.path
        landing_root   = var.landing_path
        batch_id       = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = "silver_dunning"
    layer = "silver"
    owner = "ow_tp"
  }
}
