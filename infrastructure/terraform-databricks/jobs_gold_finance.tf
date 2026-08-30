# gold_finance: OW_BILLING etl/legacy-extra/jobs/finance_excel_report.pl -> ow_tp.gold.*
#
# The report reads $ROOT/parsed/CUSTBILL*.psv — the denormalised CUSTBILL stream this migration
# landed as ow_tp.bronze.custbill_records — and nothing else. It is not the normalised
# ow_tp.silver.invoices, and in this estate the two populations disagree by orders of magnitude
# (.migration/05_progress.md, ANOM-DENORM-COPIES), so which one gold reads is a stated decision
# rather than an implementation detail.
#
# This job writes ow_tp.gold.finance_monthly, ow_tp.gold.finance_report_export and
# ow_tp.gold.quarantine_gold_finance, and exports the report CSV (plus the .xls copy the source
# makes with cp) under /Volumes/ow_tp/gold/exports/<ns>/gold_finance/. Every ow_tp.bronze.* and
# ow_tp.silver.* table is read-only to it: no INSERT, no UPDATE, no DELETE, no DDL. Inside its own
# two published targets the notebook does issue a DELETE — the MERGEs carry
# WHEN NOT MATCHED BY SOURCE AND t.ns = <ns> AND t._origin = 'gold_finance' THEN DELETE, so a group
# the current population no longer contains stops being published, which is what the legacy report
# would do. It is scoped to this ns and to rows this unit wrote, and the rows removed are counted in
# every run summary (0 on a stable input).
#
# max_concurrent_runs = 1: two overlapping runs would write the same
# (ns, period_month, legacy_group_key) rows and the same export file from two different reads of the
# CUSTBILL population, so the losing run's report would be a mix of both.
#
# trigger_granularity is per-batch (docs/tech-partnerships/contracts/gold_finance.json): the report
# is produced once per landed CUSTBILL batch by the run that lands it, so there is deliberately no
# schedule and no file-arrival trigger here. The legacy script's own "monthly" is a file-name
# convention with no month filter behind it, and a cron window declared here would be a period
# predicate the source does not have.

locals {
  gold_finance_unit        = "gold_finance"
  gold_finance_export_root = "/Volumes/${var.catalog}/gold/exports"
}

resource "databricks_notebook" "gold_finance" {
  source   = "${path.module}/../../databricks/notebooks/ow_tp_gold_finance.py"
  path     = "${var.notebook_root}/ow_tp_gold_finance"
  language = "PYTHON"
}

resource "databricks_workspace_file" "gold_finance_spec" {
  source = "${path.module}/../../databricks/ddl/gold_finance_spec.json"
  path   = "${var.notebook_root}/gold_finance_spec.json"
}

resource "databricks_job" "gold_finance" {
  name        = "ow_tp_${local.gold_finance_unit}"
  description = <<-EOT
    Finance billing report port: ow_tp.gold.finance_monthly, ow_tp.gold.finance_report_export,
    ow_tp.gold.quarantine_gold_finance and the exported CSV/.xls under
    ${local.gold_finance_export_root}/<ns>/gold_finance/. Reads the CUSTBILL population in
    ${var.catalog}.bronze.custbill_records read-only. MERGE on the declared key plus ns makes a
    rerun a no-op; empty input still writes a header-only report rather than nothing.
  EOT

  max_concurrent_runs = 1

  parameter {
    name    = "ns"
    default = var.ns
  }

  parameter {
    name    = "catalog"
    default = var.catalog
  }

  # The legacy script stamps its output file name with localtime. Empty keeps that behaviour (the
  # run's own date); an explicit YYYYMMDD is how a deterministic replay pins the stamp. It is a file
  # name, not a filter: the report always covers every record in the population.
  parameter {
    name    = "report_stamp"
    default = ""
  }

  # No secret is needed: the task reads and writes ow_tp Unity Catalog tables and one ow_tp volume,
  # so there is no dbutils.secrets lookup and no credential in the job definition.
  task {
    task_key = "build_${local.gold_finance_unit}"

    # No compute block: notebook tasks without a cluster run on serverless job compute.
    notebook_task {
      notebook_path = databricks_notebook.gold_finance.path
      source        = "WORKSPACE"

      # The record-type map, the CSV header, the quarantine codes and the DECIMAL(14,2) bound are
      # constants of the source script with no column behind them, so they are pinned in the frozen
      # spec and asserted at load time rather than exposed as knobs a deployed job could change
      # semantics with.
      base_parameters = {
        ns            = "{{job.parameters.ns}}"
        catalog       = "{{job.parameters.catalog}}"
        schema        = "gold"
        bronze_schema = "bronze"
        export_root   = local.gold_finance_export_root
        report_stamp  = "{{job.parameters.report_stamp}}"
        spec_path     = databricks_workspace_file.gold_finance_spec.path
        batch_id      = "{{job.run_id}}"
      }
    }

    timeout_seconds = 7200
  }

  queue {
    enabled = true
  }

  tags = {
    unit  = local.gold_finance_unit
    layer = "gold"
    owner = "ow_tp"
  }
}

output "gold_finance_job_name" {
  description = "Name of the gold_finance Databricks Workflows job."
  value       = databricks_job.gold_finance.name
}

output "gold_finance_export_root" {
  description = "Volume root the gold_finance report is exported under, one <ns>/gold_finance/ prefix per namespace."
  value       = local.gold_finance_export_root
}
