# ------------------------------------------------------------------------------
# OtterWorks Messaging — Serverless / Event-Driven target (namespaced)
#
# ROW 4 — RE-ARCHITECT: notification-service -> EventBridge + SQS + Lambda.
#
# Fully serverless event-driven pipeline that mirrors the behavior of the
# in-cluster SNS->SQS consumer (modules/messaging + services/notification-service
# SqsConsumer), but with no always-on pod:
#
#   domain event --> EventBridge bus --> rule (event-type filter)
#                --> SQS queue (+ DLQ) --> Lambda (reuses NotificationService)
#                --> DynamoDB notifications table (same table, no schema change)
#
# Every resource is suffixed with var.namespace so concurrent/repeat migration
# runs never collide. This module is ADDED ALONGSIDE modules/messaging; it does
# not read, replace, or modify any resource in that module. Revert is a single
# `terraform destroy -target=module.messaging_serverless_<ns>`.
# ------------------------------------------------------------------------------

locals {
  ns          = var.namespace
  name_prefix = "${var.project}-notification-${var.namespace}"

  # The preferences table is a shared, pre-existing DynamoDB table the
  # notification logic reads (NotificationRepository.getPreferences); it is NOT
  # provisioned or modified here. We only derive its ARN to grant the Lambda
  # least-privilege read access to the SAME table the in-cluster consumer uses.
  preferences_table_arn = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.preferences_table_name}"

  common_tags = {
    Module    = "messaging-serverless"
    Project   = var.project
    Namespace = var.namespace
    Migration = "row4-notification-eventbridge-sqs-lambda"
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ------------------------------------------------------------------------------
# EventBridge — custom event bus + rule
# The bus is the serverless replacement for the SNS "events" topic. The rule's
# event pattern filters to the SAME event types the SNS->SQS subscription filters
# on today (var.notification_event_types), so the re-architected path receives an
# equivalent stream of domain events.
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_event_bus" "events" {
  name = "${var.project}-events-${var.namespace}"
  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "notifications" {
  name           = "${local.name_prefix}-rule"
  description    = "Route domain events to the serverless notification pipeline (${var.namespace})."
  event_bus_name = aws_cloudwatch_event_bus.events.name

  # Mirror the old SNS subscription's message-attribute filter on `eventType`:
  # match on the same discriminator the consumer parses out of the payload, so
  # the `$.detail` forwarded to SQS is always a parseable SqsNotificationMessage.
  event_pattern = jsonencode({
    detail = {
      eventType = var.notification_event_types
    }
  })

  tags = local.common_tags
}

# ------------------------------------------------------------------------------
# SQS — buffer between EventBridge and the Lambda (+ DLQ)
# Visibility timeout must be >= the Lambda timeout.
# ------------------------------------------------------------------------------

resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "${local.name_prefix}-dlq"
  message_retention_seconds = 1209600

  # Encrypt messages at rest (SSE-SQS). SSE-SQS is used rather than a CMK so
  # EventBridge can deliver without extra kms:GenerateDataKey grants; the events
  # carry user/file identifiers, so at-rest encryption is explicit here.
  sqs_managed_sse_enabled = true

  tags = merge(local.common_tags, { Service = "notification-service" })
}

resource "aws_sqs_queue" "notifications" {
  name = "${local.name_prefix}-queue"
  # AWS guidance for a Lambda SQS event-source mapping: set the queue visibility
  # timeout to at least 6x the function timeout so in-flight messages are not
  # redelivered (and re-processed) while a batch is still being handled.
  visibility_timeout_seconds = max(var.lambda_timeout_seconds * 6, 180)
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq.arn
    maxReceiveCount     = 3
  })

  # Encrypt messages at rest (SSE-SQS); see the DLQ note above.
  sqs_managed_sse_enabled = true

  tags = merge(local.common_tags, { Service = "notification-service" })
}

# Allow EventBridge to deliver into the queue (scoped to this rule only).
resource "aws_sqs_queue_policy" "notifications" {
  queue_url = aws_sqs_queue.notifications.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.notifications.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.notifications.arn } }
    }]
  })
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule           = aws_cloudwatch_event_rule.notifications.name
  event_bus_name = aws_cloudwatch_event_bus.events.name
  target_id      = "${local.name_prefix}-sqs"
  arn            = aws_sqs_queue.notifications.arn

  # Forward only the event detail so the SQS body is the same domain-event JSON
  # shape the in-cluster consumer already parses (SqsNotificationMessage).
  input_path = "$.detail"

  dead_letter_config {
    arn = aws_sqs_queue.notifications_dlq.arn
  }
}

# ------------------------------------------------------------------------------
# IAM — least privilege for the Lambda
# Only: write its own logs, drain its own SQS queue, read/write the notifications
# DynamoDB table (+ its GSIs), and send email via SES.
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid    = "Logs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name_prefix}*"]
  }

  statement {
    sid    = "DrainQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.notifications.arn]
  }

  statement {
    sid    = "NotificationsTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
    ]
    resources = [
      var.notifications_table_arn,
      "${var.notifications_table_arn}/index/*",
    ]
  }

  # The consumer reads per-user channel preferences (NotificationService ->
  # NotificationRepository.getPreferences) but never writes them, so GetItem
  # only. The preferences table is pre-existing/shared and is not managed here.
  statement {
    sid       = "PreferencesTableRead"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [local.preferences_table_arn]
  }

  # Scope SES to ONLY the notification sender identity (least privilege): the
  # Lambda can send as var.ses_from_email but not impersonate any other verified
  # identity in the account, and the FromAddress condition pins the envelope
  # sender too.
  statement {
    sid       = "SendEmail"
    effect    = "Allow"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["arn:aws:ses:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_from_email}"]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.ses_from_email]
    }
  }

  # Decrypt the Lambda's own env vars at runtime (they are encrypted with the
  # pipeline CMK). Scoped to that single key.
  statement {
    sid       = "DecryptEnv"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.notifications.arn]
  }

  # Emit X-Ray trace segments (X-Ray has no resource-level scoping).
  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name_prefix}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ------------------------------------------------------------------------------
# KMS — customer-managed key encrypting this pipeline's data at rest (the Lambda
# environment variables and the Lambda CloudWatch log group). Namespaced so each
# migration run owns its own key. The key policy grants the account root admin
# rights and lets the CloudWatch Logs service in this region use the key for the
# Lambda's log group only (least privilege).
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "AccountRootAdmin"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid    = "CloudWatchLogsUse"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.name}.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name_prefix}-consumer"]
    }
  }
}

resource "aws_kms_key" "notifications" {
  description             = "CMK for the serverless notification pipeline (${var.namespace}): Lambda env + log group encryption."
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "notifications" {
  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.notifications.key_id
}

# ------------------------------------------------------------------------------
# Lambda — reuses the existing NotificationService logic (no rewrite of the
# notification behavior; same DynamoDB table, same rendering/preferences).
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}-consumer"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.notifications.arn
  tags              = local.common_tags
}

resource "aws_lambda_function" "consumer" {
  function_name = "${local.name_prefix}-consumer"
  role          = aws_iam_role.lambda.arn
  runtime       = var.lambda_runtime
  handler       = var.lambda_handler
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  filename         = var.lambda_jar_path
  source_code_hash = filebase64sha256(var.lambda_jar_path)

  # Encrypt environment variables at rest with the pipeline's own CMK.
  kms_key_arn = aws_kms_key.notifications.arn

  environment {
    variables = {
      DYNAMODB_TABLE_NOTIFICATIONS = var.notifications_table_name
      DYNAMODB_TABLE_PREFERENCES   = var.preferences_table_name
      SES_FROM_EMAIL               = var.ses_from_email
      AWS_REGION_OVERRIDE          = data.aws_region.current.name
      # The Lambda IS the consumer; the in-cluster poller must stay off wherever
      # this path is active.
      NOTIFICATION_CONSUMER_MODE = "serverless"
    }
  }

  # End-to-end request tracing (EventBridge -> SQS -> Lambda -> DynamoDB/SES).
  tracing_config {
    mode = "Active"
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
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}
