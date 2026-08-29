# bronze_custbill — CUSTBILL fixed-width feed into ow_tp.bronze.custbill_records.
#
# Replaces the CUSTBILL leg of the nightly batch chain (sftp_ingest_poll.ksh ->
# parse_custbill_fixedwidth.sh). Serverless notebook task only: no cluster, no
# hourly-floor resource. Shared catalog/warehouse/volume values come from this
# stack's variables rather than being hardcoded here.

locals {
  bronze_custbill_unit    = "bronze_custbill"
  bronze_custbill_landing = "${var.landing_path}/${var.ns}/custbill"
}

resource "databricks_notebook" "bronze_custbill" {
  path     = "${var.notebook_root}/bronze_custbill"
  language = "PYTHON"
  source   = "${path.module}/../../pipelines/databricks/bronze_custbill/notebooks/bronze_custbill.py"
}

resource "databricks_job" "bronze_custbill" {
  name        = "ow_tp_${local.bronze_custbill_unit}"
  description = <<-EOT
    Ingests the CUSTBILL fixed-width drop (copybook CBCUST01) into
    ${var.catalog}.bronze.custbill_records, quarantining rejected records into
    ${var.catalog}.bronze.quarantine_bronze_custbill. MERGE on (ns, record_uid)
    makes a rerun a no-op; an empty landing prefix is a no-op poll.
  EOT

  # Serverless: no job_clusters, no new_cluster, no existing_cluster_id.
  max_concurrent_runs = 1

  queue {
    enabled = true
  }

  parameter {
    name    = "ns"
    default = var.ns
  }

  task {
    task_key = "load_${local.bronze_custbill_unit}"

    notebook_task {
      notebook_path = databricks_notebook.bronze_custbill.path
      base_parameters = {
        ns = "{{job.parameters.ns}}"
      }
    }
  }

  # trigger_granularity is per-file: the job wakes on arrival in its own
  # namespaced landing prefix instead of on a nightly cron window.
  trigger {
    pause_status = "UNPAUSED"

    file_arrival {
      url                               = local.bronze_custbill_landing
      min_time_between_triggers_seconds = 60
    }
  }
}

output "bronze_custbill_job_name" {
  description = "Name of the bronze_custbill Databricks Workflows job."
  value       = databricks_job.bronze_custbill.name
}

output "bronze_custbill_landing_prefix" {
  description = "Namespaced landing prefix the bronze_custbill job polls."
  value       = local.bronze_custbill_landing
}
