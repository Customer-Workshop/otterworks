# silver_invoicing: OW_BILLING invoicing engine -> ow_tp.silver.*
#
# Serverless-only, ns-parameterised, and MERGE-idempotent: reruns merge on the natural key plus ns
# so a run only ever touches its own slice, and the invoice-line rebuild deletes only within that
# slice and only the lines the rebuild does not re-emit.

resource "databricks_notebook" "silver_invoicing" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_silver_invoicing.py"
  path     = "${var.notebook_root}/ow_tp_silver_invoicing"
  language = "PYTHON"
}

resource "databricks_workspace_file" "silver_invoicing_spec" {
  source = "${path.module}/../../databricks/ddl/silver_invoicing_spec.json"
  path   = "${var.notebook_root}/silver_invoicing_spec.json"
}

resource "databricks_job" "silver_invoicing" {
  name        = "ow_tp_silver_invoicing"
  description = "Silver invoicing engine port for invoices, invoice_lines, credit_applications, and quarantine_silver_invoicing."

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

  # No secret is needed: this reads only ow_tp.bronze.* Unity Catalog tables and writes only this
  # unit's four ow_tp.silver.* targets, so there is no dbutils.secrets lookup or credential.
  task {
    task_key = "invoice"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.silver_invoicing.path
      source        = "WORKSPACE"

      # The tax rate is not a job parameter. It is a constant of the source package body with no
      # column in the source schema or in bronze, so it is pinned in the frozen spec and asserted at
      # load time rather than exposed as a knob the deployed job could reprice money with.
      base_parameters = {
        ns            = "{{job.parameters.ns}}"
        catalog       = "{{job.parameters.catalog}}"
        schema        = "silver"
        bronze_schema = "bronze"
        period_start  = "{{job.parameters.period_start}}"
        period_end    = "{{job.parameters.period_end}}"
        spec_path     = databricks_workspace_file.silver_invoicing_spec.path
        landing_root  = var.landing_path
        batch_id      = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = "silver_invoicing"
    layer = "silver"
    owner = "ow_tp"
  }
}
