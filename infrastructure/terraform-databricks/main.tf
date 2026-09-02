resource "databricks_catalog" "ow_tp" {
  name    = "ow_tp"
  comment = "OtterWorks tech-partnerships CUSTBILL migration objects"

  # The catalog is shared with sibling showcases and adopted via import.sh;
  # metastore-assigned storage and account defaults must never force a replace.
  lifecycle {
    ignore_changes = [storage_root, storage_location, properties, comment, owner, isolation_mode, enable_predictive_optimization]
  }
}

resource "databricks_schema" "ow_tp_bronze" {
  catalog_name = databricks_catalog.ow_tp.name
  name         = "bronze"
  comment      = "Raw landed CUSTBILL records"

  lifecycle {
    ignore_changes = [comment, owner, properties]
  }
}

resource "databricks_schema" "ow_tp_silver" {
  catalog_name = databricks_catalog.ow_tp.name
  name         = "silver"
  comment      = "Parsed and quarantined CUSTBILL records"

  lifecycle {
    ignore_changes = [comment, owner, properties]
  }
}

resource "databricks_schema" "ow_tp_gold" {
  catalog_name = databricks_catalog.ow_tp.name
  name         = "gold"
  comment      = "Finance-facing CUSTBILL aggregates"

  lifecycle {
    ignore_changes = [comment, owner, properties]
  }
}

resource "databricks_volume" "ow_tp_bronze_landing" {
  catalog_name = databricks_catalog.ow_tp.name
  schema_name  = databricks_schema.ow_tp_bronze.name
  name         = "landing"
  volume_type  = "MANAGED"
  comment      = "Landing files and finance exports for the CUSTBILL workflow"

  lifecycle {
    ignore_changes = [comment, owner]
  }
}

resource "databricks_secret_scope" "ow_tp" {
  name = "ow_tp"
}

resource "databricks_secret" "sftp_host" {
  scope        = databricks_secret_scope.ow_tp.name
  key          = "sftp_host"
  string_value = var.sftp_host
}

resource "databricks_secret" "sftp_user" {
  scope        = databricks_secret_scope.ow_tp.name
  key          = "sftp_user"
  string_value = var.sftp_user
}

resource "databricks_secret" "sftp_password" {
  scope        = databricks_secret_scope.ow_tp.name
  key          = "sftp_password"
  string_value = var.sftp_password
}

resource "databricks_sql_table" "custbill_raw" {
  catalog_name       = databricks_catalog.ow_tp.name
  schema_name        = databricks_schema.ow_tp_bronze.name
  name               = "custbill_raw"
  table_type         = "MANAGED"
  data_source_format = "DELTA"
  warehouse_id       = var.warehouse_id

  column {
    name    = "ns"
    type    = "STRING"
    comment = "Migration namespace"
  }
  column {
    name    = "source_file"
    type    = "STRING"
    comment = "CUSTBILL extract file name as dropped by the mainframe"
  }
  column {
    name    = "line_no"
    type    = "INT"
    comment = "One-based source line ordinal"
  }
  column {
    name    = "record_kind"
    type    = "STRING"
    comment = "HDR, TRL, or BODY"
  }
  column {
    name    = "raw_line"
    type    = "STRING"
    comment = "Untouched fixed-width record"
  }
  column {
    name    = "file_sha256"
    type    = "STRING"
    comment = "SHA-256 of the complete landed source file"
  }
  column {
    name    = "ingested_at"
    type    = "TIMESTAMP"
    comment = "Target ingestion timestamp"
  }
}

resource "databricks_sql_table" "custbill_records" {
  catalog_name       = databricks_catalog.ow_tp.name
  schema_name        = databricks_schema.ow_tp_silver.name
  name               = "custbill_records"
  table_type         = "MANAGED"
  data_source_format = "DELTA"
  warehouse_id       = var.warehouse_id

  column {
    name    = "ns"
    type    = "STRING"
    comment = "Migration namespace"
  }
  column {
    name    = "source_file"
    type    = "STRING"
    comment = "Source CUSTBILL file basename"
  }
  column {
    name    = "line_no"
    type    = "INT"
    comment = "One-based source line ordinal"
  }
  column {
    name    = "cust_id"
    type    = "STRING"
    comment = "CUST-ID bytes 1-10, trailing spaces trimmed"
  }
  column {
    name    = "cust_name"
    type    = "STRING"
    comment = "CUST-NAME bytes 11-40, trailing spaces trimmed"
  }
  column {
    name    = "bill_date"
    type    = "DATE"
    comment = "BILL-DATE bytes 41-48, typed calendar date"
  }
  column {
    name    = "bill_amt"
    type    = "DECIMAL(12,2)"
    comment = "BILL-AMT bytes 49-60, implied decimal"
  }
  column {
    name    = "currency"
    type    = "STRING"
    comment = "CURRENCY bytes 61-63"
  }
  column {
    name    = "rec_type"
    type    = "STRING"
    comment = "REC-TYPE bytes 64-65; 01 invoice and 02 credit"
  }
  column {
    name    = "parsed_at"
    type    = "TIMESTAMP"
    comment = "Target parse timestamp"
  }
}

resource "databricks_sql_table" "custbill_quarantine" {
  catalog_name       = databricks_catalog.ow_tp.name
  schema_name        = databricks_schema.ow_tp_silver.name
  name               = "custbill_quarantine"
  table_type         = "MANAGED"
  data_source_format = "DELTA"
  warehouse_id       = var.warehouse_id

  column {
    name    = "ns"
    type    = "STRING"
    comment = "Migration namespace"
  }
  column {
    name    = "source_file"
    type    = "STRING"
    comment = "Source CUSTBILL file basename"
  }
  column {
    name    = "line_no"
    type    = "INT"
    comment = "One-based source line ordinal; zero for file-level defects"
  }
  column {
    name    = "raw_line"
    type    = "STRING"
    comment = "Original fixed-width line or file-level diagnostic"
  }
  column {
    name    = "reason"
    type    = "STRING"
    comment = "short_record|nonnumeric_amount|invalid_calendar_date|trailer_count_mismatch"
  }
  column {
    name    = "detected_at"
    type    = "TIMESTAMP"
    comment = "Target detection timestamp"
  }
}

resource "databricks_sql_table" "finance_billing" {
  catalog_name       = databricks_catalog.ow_tp.name
  schema_name        = databricks_schema.ow_tp_gold.name
  name               = "finance_billing"
  table_type         = "MANAGED"
  data_source_format = "DELTA"
  warehouse_id       = var.warehouse_id

  column {
    name    = "ns"
    type    = "STRING"
    comment = "Migration namespace"
  }
  column {
    name    = "currency"
    type    = "STRING"
    comment = "Currency code from PSV column 5"
  }
  column {
    name    = "record_type"
    type    = "STRING"
    comment = "INVOICE, CREDIT, or UNKNOWN(xx)"
  }
  column {
    name    = "record_count"
    type    = "BIGINT"
    comment = "Count of records in the currency and record-type group"
  }
  column {
    name    = "total_amount"
    type    = "DECIMAL(18,2)"
    comment = "Decimal total corresponding to legacy %.2f amount output"
  }
  column {
    name    = "report_date"
    type    = "DATE"
    comment = "Finance report date"
  }
  column {
    name    = "generated_at"
    type    = "TIMESTAMP"
    comment = "Target report generation timestamp"
  }
}

resource "databricks_notebook" "ingest" {
  path     = "/Shared/ow_tp/custbill/ingest"
  language = "PYTHON"
  format   = "SOURCE"
  source   = "${path.module}/notebooks/ingest.py"
}

resource "databricks_notebook" "parse" {
  path     = "/Shared/ow_tp/custbill/parse"
  language = "PYTHON"
  format   = "SOURCE"
  source   = "${path.module}/notebooks/parse.py"
}

resource "databricks_notebook" "finance" {
  path     = "/Shared/ow_tp/custbill/finance"
  language = "PYTHON"
  format   = "SOURCE"
  source   = "${path.module}/notebooks/finance.py"
}

resource "databricks_job" "ow_tp_custbill" {
  name                = "ow_tp_custbill"
  max_concurrent_runs = 1

  parameter {
    name    = "ns"
    default = "demo"
  }

  parameter {
    name    = "report_date"
    default = ""
  }

  task {
    task_key                  = "finance"
    max_retries               = 2
    min_retry_interval_millis = 300000
    retry_on_timeout          = false
    depends_on {
      task_key = "parse"
    }
    notebook_task {
      notebook_path = databricks_notebook.finance.path
      base_parameters = {
        ns          = "{{job.parameters.ns}}"
        report_date = "{{job.parameters.report_date}}"
      }
    }
    environment_key = "default"
  }

  task {
    task_key                  = "ingest"
    max_retries               = 2
    min_retry_interval_millis = 300000
    retry_on_timeout          = false
    notebook_task {
      notebook_path   = databricks_notebook.ingest.path
      base_parameters = { ns = "{{job.parameters.ns}}" }
    }
    environment_key = "default"
  }

  task {
    task_key                  = "parse"
    max_retries               = 2
    min_retry_interval_millis = 300000
    retry_on_timeout          = false
    depends_on {
      task_key = "ingest"
    }
    notebook_task {
      notebook_path   = databricks_notebook.parse.path
      base_parameters = { ns = "{{job.parameters.ns}}" }
    }
    environment_key = "default"
  }

  environment {
    environment_key = "default"
    spec {
      client = "1"
    }
  }

  schedule {
    quartz_cron_expression = "0 */15 * * * ?"
    timezone_id            = "UTC"
    pause_status           = "PAUSED"
  }

  email_notifications {
    on_failure = var.finance_recipients
  }
}
