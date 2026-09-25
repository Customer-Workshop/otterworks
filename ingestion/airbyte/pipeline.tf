# Airbyte Cloud: S3 landing zone -> Databricks (ow_tp catalog).

resource "airbyte_source_s3" "billing_landing" {
  name         = "${local.prefix}-billing-landing"
  workspace_id = var.airbyte_workspace_id

  configuration = {
    bucket                = aws_s3_bucket.landing.bucket
    region_name           = var.aws_region
    aws_access_key_id     = aws_iam_access_key.airbyte_reader.id
    aws_secret_access_key = aws_iam_access_key.airbyte_reader.secret

    streams = [
      for table, _ in var.streams : {
        name  = table
        globs = ["${var.namespace}/${table}/*.csv"]
        format = {
          csv_format = {
            # Legacy exports are written verbatim; typing happens in the lakehouse.
            # An empty field is a NULL, never a value.
            null_values = [""]
          }
        }
      }
    ]
  }
}

resource "airbyte_destination_databricks" "lakehouse" {
  name         = "${local.prefix}-lakehouse"
  workspace_id = var.airbyte_workspace_id

  configuration = {
    accept_terms        = true
    hostname            = local.databricks_hostname
    http_path           = "/sql/1.0/warehouses/${var.databricks_warehouse_id}"
    database            = var.databricks_catalog
    schema              = "airbyte_${var.namespace}"
    raw_schema_override = "airbyte_${var.namespace}_raw"

    authentication = {
      o_auth2_recommended = {
        client_id = var.databricks_client_id
        secret    = var.databricks_client_secret
      }
    }
  }
}

resource "airbyte_connection" "billing" {
  name           = "${local.prefix}-billing"
  source_id      = airbyte_source_s3.billing_landing.source_id
  destination_id = airbyte_destination_databricks.lakehouse.destination_id

  namespace_definition                 = "destination"
  non_breaking_schema_updates_behavior = "propagate_columns"

  schedule = {
    schedule_type   = "cron"
    cron_expression = var.sync_cron
  }

  configurations = {
    streams = [
      for table, cfg in var.streams : {
        name      = table
        sync_mode = cfg.sync_mode
        # The S3 source defines its own cursor; the API echoes it back even for
        # full-refresh streams, so state it to keep the plan clean.
        cursor_field = length(cfg.cursor_field) > 0 ? cfg.cursor_field : ["_ab_source_file_last_modified"]
        primary_key  = length(cfg.primary_key) > 0 ? [for f in cfg.primary_key : [f]] : null
        mappers = length(lookup(var.hashed_fields, table, [])) > 0 ? [
          for field in var.hashed_fields[table] : {
            type = "hashing"
            mapper_configuration = {
              hashing = {
                method            = "SHA-256"
                target_field      = field
                field_name_suffix = var.hashed_field_suffix
              }
            }
          }
        ] : null
      }
    ]
  }
}
