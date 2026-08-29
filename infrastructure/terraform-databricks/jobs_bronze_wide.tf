# bronze_wide — the wide/denormalised OW_BILLING surfaces (155-column
# CUSTOMER_MASTER, ENTITY_ATTR_VALUE, INVOICE_LINE, INVOICE_HEADER) plus their
# quarantine table. Serverless notebook task only: no cluster, no warehouse and
# no other hourly-cost resource is declared here, and the shared objects in
# main.tf are consumed, not redefined.

locals {
  bronze_wide_unit          = "bronze_wide"
  bronze_wide_notebook_path = "${var.notebook_root}/ow_tp_bronze_wide"
}

resource "databricks_notebook" "bronze_wide" {
  path     = local.bronze_wide_notebook_path
  language = "PYTHON"
  source   = "${path.module}/../../pipelines/databricks/bronze_wide/ow_tp_bronze_wide.py"
}

resource "databricks_job" "bronze_wide" {
  name        = "ow_tp_${local.bronze_wide_unit}"
  description = <<-EOT
    Loads the OW_BILLING wide/denormalised surfaces into ${var.catalog}.bronze.
    Delta MERGE on (ns, natural key), so a second identical run is a no-op.
    Unparseable VARCHAR2(9) dates are quarantined with a closed reason code and
    counted; loaded + quarantined always equals the source row count.
  EOT

  # Namespace is a job parameter so one job definition serves every run slice;
  # every target row and every volume path carries it.
  parameter {
    name    = "ns"
    default = var.ns
  }

  parameter {
    name    = "landing_root"
    default = var.landing_path
  }

  parameter {
    name    = "catalog"
    default = data.databricks_catalog.shared.name
  }

  parameter {
    name    = "schema"
    default = data.databricks_schema.bronze.name
  }

  task {
    task_key = "load_bronze_wide"

    # No job_cluster_key and no existing_cluster_id: the task runs on
    # serverless compute for notebooks.
    notebook_task {
      notebook_path = databricks_notebook.bronze_wide.path
      source        = "WORKSPACE"

      base_parameters = {
        ns           = "{{job.parameters.ns}}"
        landing_root = "{{job.parameters.landing_root}}"
        catalog      = "{{job.parameters.catalog}}"
        schema       = "{{job.parameters.schema}}"
      }
    }
  }

  queue {
    enabled = true
  }

  max_concurrent_runs = 1
}
