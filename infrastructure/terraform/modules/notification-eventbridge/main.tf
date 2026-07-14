# ------------------------------------------------------------------------------
# OtterWorks Notification EventBridge Module
#
# Re-architects notification delivery onto a serverless, event-driven pipeline:
#
#   domain event  --PutEvents-->  EventBridge (custom bus)
#                                        |  rule (source + detail-type match)
#                                        v
#                                     SQS queue  --(+ DLQ, maxReceiveCount=3)
#                                        |  event source mapping
#                                        v
#                                  Lambda consumer  --> DynamoDB notifications
#
# This module sits ALONGSIDE modules/messaging (SNS -> SQS -> in-cluster
# consumer), which remains the default on `main`. Everything here is namespaced
# with `var.ns` so concurrent migrations never collide, and IAM is scoped to
# exactly what the Lambda needs (least privilege).
# ------------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  suffix      = "${var.environment}-${var.ns}"
  name_prefix = "${var.project}-notifications-eb-${local.suffix}"

  account_id = var.aws_account_id != "" ? var.aws_account_id : data.aws_caller_identity.current.account_id
  region     = var.aws_region

  notifications_table_arn = var.notifications_table_arn != "" ? var.notifications_table_arn : "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.notifications_table_name}"
  preferences_table_arn   = var.preferences_table_arn != "" ? var.preferences_table_arn : "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.preferences_table_name}"

  common_tags = merge(var.tags, {
    Module      = "notification-eventbridge"
    Project     = var.project
    Environment = var.environment
    Namespace   = var.ns
    Migration   = "rearchitect-notification-delivery"
  })
}

# --- EventBridge custom bus + rule -------------------------------------------

resource "aws_cloudwatch_event_bus" "notifications" {
  name = local.name_prefix
  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "notifications" {
  name           = "${local.name_prefix}-rule"
  description    = "Route OtterWorks domain events to the serverless notification pipeline (${var.ns})"
  event_bus_name = aws_cloudwatch_event_bus.notifications.name

  event_pattern = jsonencode({
    source        = var.event_source_names
    "detail-type" = var.event_detail_types
  })

  tags = local.common_tags
}

# --- SQS queue + DLQ ----------------------------------------------------------

resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "${local.name_prefix}-dlq"
  message_retention_seconds = 1209600
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "notifications" {
  name                       = local.name_prefix
  visibility_timeout_seconds = var.lambda_timeout_seconds * 6
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule           = aws_cloudwatch_event_rule.notifications.name
  event_bus_name = aws_cloudwatch_event_bus.notifications.name
  target_id      = "${local.name_prefix}-sqs"
  arn            = aws_sqs_queue.notifications.arn
}

# Allow EventBridge to deliver matched events to the queue (scoped to this rule).
resource "aws_sqs_queue_policy" "notifications" {
  queue_url = aws_sqs_queue.notifications.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgeToSendMessage"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.notifications.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.notifications.arn } }
    }]
  })
}

# --- Encryption key (log group + Lambda env vars) -----------------------------

# Customer-managed KMS key so the Lambda log group and environment variables are
# encrypted with a key we control (rather than the AWS-managed default).
resource "aws_kms_key" "this" {
  description             = "OtterWorks notification EventBridge pipeline (${var.ns})"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccount"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowCloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${local.region}.amazonaws.com" }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.name_prefix}-consumer"
          }
        }
      },
    ]
  })

  tags = local.common_tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

# --- Lambda consumer ----------------------------------------------------------

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/${local.name_prefix}-lambda.zip"
  excludes    = ["test_handler.py", "__pycache__", "README.md"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}-consumer"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.this.arn
  tags              = local.common_tags
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-consumer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

# Least privilege: only the SQS queue, the two DynamoDB tables, SES send, and
# this function's own log group. No wildcards beyond SES (which requires "*").
resource "aws_iam_role_policy" "lambda" {
  name = "${local.name_prefix}-consumer-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ConsumeQueue"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = [aws_sqs_queue.notifications.arn]
      },
      {
        Sid    = "WriteNotifications"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
        ]
        Resource = [
          local.notifications_table_arn,
          "${local.notifications_table_arn}/index/*",
          local.preferences_table_arn,
        ]
      },
      {
        Sid      = "SendEmail"
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = ["*"]
      },
      {
        Sid      = "DecryptEnv"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.this.arn]
      },
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
        ]
        Resource = ["*"]
      },
      {
        Sid    = "WriteLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
      },
    ]
  })
}

resource "aws_lambda_function" "consumer" {
  function_name    = "${local.name_prefix}-consumer"
  role             = aws_iam_role.lambda.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  kms_key_arn      = aws_kms_key.this.arn

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      DYNAMODB_TABLE_NOTIFICATIONS = var.notifications_table_name
      DYNAMODB_TABLE_PREFERENCES   = var.preferences_table_name
      SES_FROM_EMAIL               = var.ses_from_email
      EMAIL_DELIVERY_ENABLED       = "true"
      AWS_ENDPOINT_URL             = var.aws_endpoint_url
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = local.common_tags
}

resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn                   = aws_sqs_queue.notifications.arn
  function_name                      = aws_lambda_function.consumer.arn
  batch_size                         = var.lambda_batch_size
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}
