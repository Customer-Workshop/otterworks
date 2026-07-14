# ------------------------------------------------------------------------------
# OtterWorks Analytics Lakehouse Module
#
# RE-ARCHITECT target for the analytics-service persistence: an S3 data lake in
# Apache Iceberg table format, cataloged in AWS Glue and queried with Amazon
# Athena. This module is ADDITIVE and fully namespaced (var.namespace) — it never
# replaces the durable PostgreSQL "before" and touches no shared/main resources.
#
# Storage reuses the existing analytics data-lake bucket (from the storage
# module) under a dedicated warehouse prefix, so the app is wired through the
# same analytics.s3.data-lake-bucket config it already exposes.
# ------------------------------------------------------------------------------

locals {
  ns          = var.namespace
  name_prefix = "${var.project}-analytics-lakehouse-${local.ns}"
  # Glue database names must be lowercase and use underscores.
  glue_database   = "${replace(var.project, "-", "_")}_analytics_${local.ns}"
  warehouse_s3    = "s3://${var.data_lake_bucket_name}/${var.warehouse_prefix}-${local.ns}"
  table_location  = "${local.warehouse_s3}/${var.events_table_name}"
  athena_results  = "s3://${aws_s3_bucket.athena_results.id}/results/"
  warehouse_arn_g = "${var.data_lake_bucket_arn}/${var.warehouse_prefix}-${local.ns}/*"

  common_tags = {
    Module    = "analytics_lakehouse"
    Project   = var.project
    Namespace = local.ns
    Migration = "analytics-persistence-to-iceberg"
  }
}

# --- Athena query-results bucket (namespaced, private, encrypted) ---

resource "aws_s3_bucket" "athena_results" {
  bucket = "${local.name_prefix}-athena-${var.environment}"

  tags = merge(local.common_tags, {
    Service = "analytics-service"
    Purpose = "athena-query-results"
  })
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}

# --- Glue Data Catalog: database + Iceberg table ---

resource "aws_glue_catalog_database" "analytics" {
  name        = local.glue_database
  description = "Iceberg catalog for the analytics lakehouse (namespace ${local.ns})."

  tags = local.common_tags
}

# Register the event log as an Iceberg table in Glue. Athena/Spark evolve the
# schema and manage snapshots from here; the Iceberg writer in analytics-service
# appends data files under the table location.
resource "aws_glue_catalog_table" "analytics_events" {
  name          = var.events_table_name
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  open_table_format_input {
    iceberg_input {
      metadata_operation = "CREATE"
      version            = "2"
    }
  }

  storage_descriptor {
    location = local.table_location

    columns {
      name = "seq"
      type = "bigint"
    }
    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "event_type"
      type = "string"
    }
    columns {
      name = "user_id"
      type = "string"
    }
    columns {
      name = "resource_id"
      type = "string"
    }
    columns {
      name = "resource_type"
      type = "string"
    }
    columns {
      name = "metadata"
      type = "map<string,string>"
    }
    columns {
      name = "occurred_at"
      type = "bigint"
    }
    columns {
      name = "event_date"
      type = "string"
    }
  }
}

# --- Athena workgroup (namespaced, results to the dedicated bucket) ---

resource "aws_athena_workgroup" "analytics" {
  name = local.name_prefix

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = local.athena_results
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  force_destroy = true
  tags          = local.common_tags
}

# --- Least-privilege IAM policy for the lakehouse backend ---
# Scoped to exactly this namespace's Glue database/table, Athena workgroup, and
# the data-lake warehouse prefix + results bucket. No wildcards over shared data.

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lakehouse" {
  statement {
    sid    = "GlueCatalogAccess"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:UpdatePartition",
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/${local.glue_database}",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${local.glue_database}/*",
    ]
  }

  statement {
    sid    = "AthenaQuery"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
    ]
    resources = [aws_athena_workgroup.analytics.arn]
  }

  statement {
    sid    = "WarehouseObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      local.warehouse_arn_g,
      "${aws_s3_bucket.athena_results.arn}/*",
    ]
  }

  statement {
    sid    = "WarehouseList"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = [
      var.data_lake_bucket_arn,
      aws_s3_bucket.athena_results.arn,
    ]
  }
}

resource "aws_iam_policy" "lakehouse" {
  name        = "${local.name_prefix}-${var.environment}"
  description = "Least-privilege Glue/Athena/S3 access for the namespaced analytics Iceberg lakehouse."
  policy      = data.aws_iam_policy_document.lakehouse.json

  tags = local.common_tags
}
