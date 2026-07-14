data "aws_caller_identity" "current" {}

locals {
  resource_name    = "${var.project}-analytics-${var.environment}-${var.namespace}"
  bucket_name      = "${local.resource_name}-${data.aws_caller_identity.current.account_id}"
  database_name    = "${replace(var.project, "-", "_")}_analytics_${var.environment}_${var.namespace}"
  events_table     = "analytics_events_${var.namespace}"
  aggregates_table = "analytics_daily_metrics_${var.namespace}"
  workgroup_name   = "${local.resource_name}-wg"
  query_output     = "s3://${aws_s3_bucket.lakehouse.id}/query-results/"
  warehouse        = "s3://${aws_s3_bucket.lakehouse.id}/warehouse/"

  events_ddl = <<-SQL
    CREATE TABLE IF NOT EXISTS ${local.database_name}.${local.events_table} (
      seq_no bigint,
      event_id string,
      event_type string,
      user_id string,
      resource_id string,
      resource_type string,
      metadata string,
      occurred_at bigint,
      event_date string
    )
    PARTITIONED BY (event_type)
    LOCATION '${local.warehouse}${local.events_table}/'
    TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet')
  SQL

  aggregates_ddl = <<-SQL
    CREATE TABLE IF NOT EXISTS ${local.database_name}.${local.aggregates_table} (
      event_date string,
      event_type string,
      event_count bigint
    )
    PARTITIONED BY (event_date)
    LOCATION '${local.warehouse}${local.aggregates_table}/'
    TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet')
  SQL
}

resource "aws_s3_bucket" "lakehouse" {
  bucket        = local.bucket_name
  force_destroy = true

  tags = {
    Module    = "analytics-iceberg-${var.namespace}"
    Service   = "analytics-service"
    Namespace = var.namespace
  }
}

resource "aws_s3_bucket_public_access_block" "lakehouse" {
  bucket                  = aws_s3_bucket.lakehouse.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"

    filter {
      prefix = "query-results/"
    }

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

data "aws_iam_policy_document" "lakehouse" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.lakehouse.arn,
      "${aws_s3_bucket.lakehouse.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  policy = data.aws_iam_policy_document.lakehouse.json
}

resource "aws_glue_catalog_database" "lakehouse" {
  name         = local.database_name
  location_uri = local.warehouse
}

resource "aws_athena_workgroup" "lakehouse" {
  name          = local.workgroup_name
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = local.query_output
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = {
    Module    = "analytics-iceberg-${var.namespace}"
    Service   = "analytics-service"
    Namespace = var.namespace
  }
}

resource "terraform_data" "iceberg_tables" {
  triggers_replace = [
    local.events_ddl,
    local.aggregates_ddl,
    aws_athena_workgroup.lakehouse.name,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      AWS_REGION     = var.aws_region
      DATABASE       = aws_glue_catalog_database.lakehouse.name
      WORKGROUP      = aws_athena_workgroup.lakehouse.name
      EVENTS_DDL     = local.events_ddl
      AGGREGATES_DDL = local.aggregates_ddl
    }
    command = <<-BASH
      set -euo pipefail
      run_query() {
        local query_id state reason
        query_id="$(aws athena start-query-execution \
          --region "$AWS_REGION" \
          --work-group "$WORKGROUP" \
          --query-execution-context "Database=$DATABASE" \
          --query-string "$1" \
          --query QueryExecutionId \
          --output text)"
        while true; do
          state="$(aws athena get-query-execution \
            --region "$AWS_REGION" \
            --query-execution-id "$query_id" \
            --query 'QueryExecution.Status.State' \
            --output text)"
          case "$state" in
            SUCCEEDED) return 0 ;;
            FAILED|CANCELLED)
              reason="$(aws athena get-query-execution \
                --region "$AWS_REGION" \
                --query-execution-id "$query_id" \
                --query 'QueryExecution.Status.StateChangeReason' \
                --output text)"
              echo "Athena query $query_id $state: $reason" >&2
              return 1
              ;;
          esac
          sleep 2
        done
      }
      run_query "$EVENTS_DDL"
      run_query "$AGGREGATES_DDL"
    BASH
  }

  depends_on = [
    aws_s3_bucket_policy.lakehouse,
    aws_s3_bucket_server_side_encryption_configuration.lakehouse,
  ]
}

resource "aws_athena_named_query" "daily_rollup" {
  name        = "${local.resource_name}-daily-rollup"
  database    = aws_glue_catalog_database.lakehouse.name
  workgroup   = aws_athena_workgroup.lakehouse.name
  description = "Refresh the Iceberg daily aggregate table from canonical raw events."
  query       = <<-SQL
    MERGE INTO ${local.database_name}.${local.aggregates_table} AS target
    USING (
      SELECT event_date, event_type, COUNT(*) AS event_count
      FROM ${local.database_name}.${local.events_table}
      GROUP BY event_date, event_type
    ) AS source
    ON target.event_date = source.event_date
    AND target.event_type = source.event_type
    WHEN MATCHED THEN UPDATE SET event_count = source.event_count
    WHEN NOT MATCHED THEN INSERT (event_date, event_type, event_count)
    VALUES (source.event_date, source.event_type, source.event_count)
  SQL

  depends_on = [terraform_data.iceberg_tables]
}

resource "aws_athena_named_query" "continuous_validation" {
  name        = "${local.resource_name}-continuous-validation"
  database    = aws_glue_catalog_database.lakehouse.name
  workgroup   = aws_athena_workgroup.lakehouse.name
  description = "Find persisted aggregate rows that diverge from raw Iceberg event counts."
  query       = <<-SQL
    WITH expected AS (
      SELECT event_date, event_type, COUNT(*) AS event_count
      FROM ${local.database_name}.${local.events_table}
      GROUP BY event_date, event_type
    )
    SELECT
      COALESCE(expected.event_date, actual.event_date) AS event_date,
      COALESCE(expected.event_type, actual.event_type) AS event_type,
      expected.event_count AS raw_event_count,
      actual.event_count AS aggregate_event_count
    FROM expected
    FULL OUTER JOIN ${local.database_name}.${local.aggregates_table} actual
      ON expected.event_date = actual.event_date
      AND expected.event_type = actual.event_type
    WHERE COALESCE(expected.event_count, -1) <> COALESCE(actual.event_count, -1)
  SQL

  depends_on = [terraform_data.iceberg_tables]
}

data "aws_iam_policy_document" "analytics_access" {
  statement {
    sid = "AthenaQueries"
    actions = [
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetWorkGroup",
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
    ]
    resources = [aws_athena_workgroup.lakehouse.arn]
  }

  statement {
    sid = "GlueIcebergCatalog"
    actions = [
      "glue:GetDatabase",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.lakehouse.arn,
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.database_name}/${local.events_table}",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.database_name}/${local.aggregates_table}",
    ]
  }

  statement {
    sid       = "ListLakehouseBucket"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.lakehouse.arn]
  }

  statement {
    sid = "ReadWriteIcebergObjects"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.lakehouse.arn}/*"]
  }
}

resource "aws_iam_policy" "analytics_access" {
  name        = "${local.resource_name}-access"
  description = "Least-privilege analytics-service access to the ice1 Iceberg lakehouse"
  policy      = data.aws_iam_policy_document.analytics_access.json
}

resource "aws_iam_role_policy_attachment" "analytics_access" {
  role       = var.analytics_role_name
  policy_arn = aws_iam_policy.analytics_access.arn
}
