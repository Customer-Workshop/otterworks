# ------------------------------------------------------------------------------
# OtterWorks Report Service — Serverless target (AWS Lambda + API Gateway)
#
# Namespaced migration module (suffix: var.namespace_suffix, default "lam1").
# Refactors the always-on EKS report-service pod onto Lambda + API Gateway
# (scale-to-zero, pay-per-request) WITHOUT changing the HTTP contract: the same
# Spring Boot application (ReportApplication) is wrapped by
# com.otterworks.report.lambda.StreamLambdaHandler via
# aws-serverless-java-container, so routes/response schemas/status codes are
# identical behind API Gateway.
#
# This module is ADDED ALONGSIDE the existing EKS deployment; it does not modify
# or replace any shared/`main` resource. Every resource carries the namespace
# suffix so concurrent sibling migrations never collide. Revert is a single
# `terraform destroy -target=module.report_service_lam1`.
# ------------------------------------------------------------------------------

locals {
  ns          = var.namespace_suffix
  name_prefix = "${var.project}-report-${local.ns}-${var.environment}"

  lambda_log_group_arn = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name_prefix}"
  apigw_log_group_arn  = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/${local.name_prefix}"

  common_tags = {
    Module    = "report-service-${local.ns}"
    Project   = var.project
    Service   = "report-service"
    Migration = "eks-pod-to-lambda"
    Namespace = local.ns
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# --- Customer-managed KMS key -------------------------------------------------
# One namespaced CMK encrypts the Lambda environment variables (which carry the
# DB connection settings) and both CloudWatch log groups at rest. The key policy
# delegates to account IAM (root) and additionally lets the CloudWatch Logs
# service use the key for THIS module's two log groups only (encryption-context
# scoped), so nothing outside the namespace can use it.

data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "EnableAccountIAM"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowCloudWatchLogs"
    effect    = "Allow"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.name}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["${local.lambda_log_group_arn}", "${local.apigw_log_group_arn}"]
    }
  }
}

resource "aws_kms_key" "this" {
  description             = "CMK for report-service Lambda env vars + log groups (${local.ns})"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.kms.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

# --- CloudWatch log group (own log group only) -------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.this.arn
  tags              = local.common_tags
}

# --- Least-privilege execution role ------------------------------------------

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name_prefix}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = local.common_tags
}

# Logs: scoped to this function's own log group + streams only.
data "aws_iam_policy_document" "logs" {
  statement {
    sid       = "CreateLogStreams"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "${local.name_prefix}-logs"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.logs.json
}

# VPC networking: the ENI actions Lambda needs to attach to private subnets so
# it can reach RDS + dependent services. These EC2 actions cannot be resource
# scoped by AWS; least privilege here is the minimal documented ENI action set
# (equivalent to AWSLambdaVPCAccessExecutionRole, granted explicitly).
data "aws_iam_policy_document" "vpc" {
  statement {
    sid = "ManageLambdaENIs"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "vpc" {
  name   = "${local.name_prefix}-vpc"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.vpc.json
}

# Observability: X-Ray trace publishing (no resource-level scoping in AWS) and
# decrypt of this module's own CMK so the runtime can read encrypted env vars.
data "aws_iam_policy_document" "observability" {
  statement {
    sid       = "PublishXRayTraces"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
  statement {
    sid       = "DecryptOwnCmk"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
}

resource "aws_iam_role_policy" "observability" {
  name   = "${local.name_prefix}-observability"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.observability.json
}

# --- Security group: Lambda egress only (to RDS / dependent services) --------

resource "aws_security_group" "lambda" {
  name        = "${local.name_prefix}-sg"
  description = "Egress SG for report-service Lambda (${local.ns})"
  vpc_id      = var.vpc_id

  egress {
    description = "All egress within/out of VPC (RDS, dependent services)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# --- Lambda function ----------------------------------------------------------

resource "aws_lambda_function" "report" {
  function_name = local.name_prefix
  role          = aws_iam_role.lambda_exec.arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_s

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  # Encrypt environment variables at rest with the module's own CMK.
  kms_key_arn = aws_kms_key.this.arn

  # Distributed tracing for cold-start / duration analysis of the migration.
  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      # Activates application-lambda.properties (connection-layer overlay).
      SPRING_PROFILES_ACTIVE = "lambda"
      # Lambda's only writable filesystem is /tmp.
      REPORT_OUTPUT_DIR = "/tmp/reports"

      DB_HOST     = var.db_host
      DB_PORT     = var.db_port
      DB_NAME     = var.db_name
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password

      ANALYTICS_SERVICE_URL = var.analytics_service_url
      AUDIT_SERVICE_URL     = var.audit_service_url
      AUTH_SERVICE_URL      = var.auth_service_url
    }
  }

  depends_on = [
    aws_iam_role_policy.logs,
    aws_iam_role_policy.vpc,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = local.common_tags
}

# --- API Gateway (HTTP API) fronting the Lambda ------------------------------
# payload_format_version 1.0 delivers the AWS_PROXY (v1 / AwsProxyRequest) event
# shape that aws-serverless-java-container's StreamLambdaHandler expects.

resource "aws_apigatewayv2_api" "report" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  tags          = local.common_tags
}

resource "aws_apigatewayv2_integration" "report" {
  api_id                 = aws_apigatewayv2_api.report.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.report.invoke_arn
  payload_format_version = "1.0"
  integration_method     = "POST"
}

# Catch-all proxy so EVERY report-service route (/api/v1/reports*, /health, …)
# reaches the same Spring app unchanged.
resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.report.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.report.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.report.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.report.id}"
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.this.arn
  tags              = local.common_tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.report.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLatency  = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  tags = local.common_tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowInvokeFromApiGateway-${local.ns}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.report.execution_arn}/*/*"
}
