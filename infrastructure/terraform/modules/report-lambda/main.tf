data "aws_caller_identity" "current" {}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "aws_security_group" "lambda" {
  name                   = "report-service-lambda-${var.namespace}"
  description            = "Lambda security group for report-service ${var.namespace}"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name      = "report-service-lambda-${var.namespace}"
    Namespace = var.namespace
  }
}

resource "aws_security_group" "proxy" {
  name                   = "report-service-proxy-${var.namespace}"
  description            = "RDS Proxy security group for report-service ${var.namespace}"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name      = "report-service-proxy-${var.namespace}"
    Namespace = var.namespace
  }
}

resource "aws_security_group" "database" {
  name                   = "report-service-rds-${var.namespace}"
  description            = "RDS security group for report-service ${var.namespace}"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  tags = {
    Name      = "report-service-rds-${var.namespace}"
    Namespace = var.namespace
  }
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_proxy" {
  security_group_id            = aws_security_group.lambda.id
  referenced_security_group_id = aws_security_group.proxy.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "lambda_dns_udp" {
  security_group_id = aws_security_group.lambda.id
  cidr_ipv4         = var.vpc_cidr_block
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
}

resource "aws_vpc_security_group_egress_rule" "lambda_dns_tcp" {
  security_group_id = aws_security_group.lambda.id
  cidr_ipv4         = var.vpc_cidr_block
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
}

resource "aws_vpc_security_group_ingress_rule" "proxy_from_lambda" {
  security_group_id            = aws_security_group.proxy.id
  referenced_security_group_id = aws_security_group.lambda.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "proxy_to_database" {
  security_group_id            = aws_security_group.proxy.id
  referenced_security_group_id = aws_security_group.database.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "database_from_proxy" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.proxy.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_subnet_group" "report" {
  name       = "report-service-${var.namespace}"
  subnet_ids = var.subnet_ids

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_db_instance" "report" {
  identifier             = "report-service-${var.namespace}"
  engine                 = "postgres"
  engine_version         = "15.18"
  instance_class         = var.database_instance_class
  allocated_storage      = 20
  db_name                = var.database_name
  username               = var.database_user
  password               = random_password.database.result
  publicly_accessible    = false
  apply_immediately      = true
  skip_final_snapshot    = true
  deletion_protection    = false
  db_subnet_group_name   = aws_db_subnet_group.report.name
  vpc_security_group_ids = [aws_security_group.database.id]

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_secretsmanager_secret" "database" {
  name                    = "report-service-${var.namespace}-db"
  recovery_window_in_days = 0

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    username = var.database_user
    password = random_password.database.result
  })
}

data "aws_iam_policy_document" "proxy_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "proxy" {
  name               = "report-service-proxy-${var.namespace}"
  assume_role_policy = data.aws_iam_policy_document.proxy_assume_role.json

  tags = {
    Namespace = var.namespace
  }
}

data "aws_iam_policy_document" "proxy_secret_access" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.database.arn]
  }
}

resource "aws_iam_role_policy" "proxy_secret_access" {
  name   = "read-report-db-secret-${var.namespace}"
  role   = aws_iam_role.proxy.id
  policy = data.aws_iam_policy_document.proxy_secret_access.json
}

resource "aws_db_proxy" "report" {
  name                   = "report-service-${var.namespace}"
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  role_arn               = aws_iam_role.proxy.arn
  vpc_security_group_ids = [aws_security_group.proxy.id]
  vpc_subnet_ids         = var.subnet_ids

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.database.arn
  }

  tags = {
    Namespace = var.namespace
  }

  depends_on = [aws_secretsmanager_secret_version.database]
}

resource "aws_db_proxy_default_target_group" "report" {
  db_proxy_name = aws_db_proxy.report.name

  connection_pool_config {
    max_connections_percent      = 80
    max_idle_connections_percent = 40
    connection_borrow_timeout    = 30
  }
}

resource "aws_db_proxy_target" "report" {
  db_proxy_name          = aws_db_proxy.report.name
  target_group_name      = aws_db_proxy_default_target_group.report.name
  db_instance_identifier = aws_db_instance.report.identifier
}

data "aws_iam_policy_document" "lambda_assume_role" {
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
  name               = "report-service-lambda-${var.namespace}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Namespace = var.namespace
  }
}

data "aws_iam_policy_document" "lambda_runtime" {
  statement {
    sid = "WriteFunctionLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid = "ManageVpcNetworkInterfaces"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeSubnets",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_runtime" {
  name   = "report-service-runtime-${var.namespace}"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_runtime.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/report-service-${var.namespace}"
  retention_in_days = 7

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/report-service-${var.namespace}"
  retention_in_days = 7

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_s3_bucket" "lambda_artifact" {
  bucket        = "report-service-${var.namespace}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_artifact" {
  bucket = aws_s3_bucket.lambda_artifact.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_artifact" {
  bucket = aws_s3_bucket.lambda_artifact.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "lambda_artifact" {
  bucket = aws_s3_bucket.lambda_artifact.id
  key    = "report-service-lambda.jar"
  source = var.lambda_jar_path
  etag   = filemd5(var.lambda_jar_path)
}

resource "aws_lambda_function" "report" {
  function_name                  = "report-service-${var.namespace}"
  role                           = aws_iam_role.lambda.arn
  runtime                        = "java8.al2"
  handler                        = "com.otterworks.report.lambda.StreamLambdaHandler::handleRequest"
  s3_bucket                      = aws_s3_bucket.lambda_artifact.id
  s3_key                         = aws_s3_object.lambda_artifact.key
  source_code_hash               = filebase64sha256(var.lambda_jar_path)
  memory_size                    = var.lambda_memory
  timeout                        = 30
  publish                        = true
  reserved_concurrent_executions = var.lambda_reserved_concurrency

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DB_HOST                                    = aws_db_proxy.report.endpoint
      DB_PORT                                    = "5432"
      DB_NAME                                    = var.database_name
      DB_USER                                    = var.database_user
      DB_PASSWORD                                = random_password.database.result
      SPRING_DATASOURCE_URL                      = "jdbc:postgresql://${aws_db_proxy.report.endpoint}:5432/${var.database_name}"
      SPRING_DATASOURCE_USERNAME                 = var.database_user
      SPRING_DATASOURCE_PASSWORD                 = random_password.database.result
      SPRING_DATASOURCE_DRIVER_CLASS_NAME        = "org.postgresql.Driver"
      SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT    = "org.hibernate.dialect.PostgreSQL10Dialect"
      SPRING_JPA_HIBERNATE_DDL_AUTO              = "update"
      SPRING_JPA_OPEN_IN_VIEW                    = "false"
      SPRING_MAIN_LAZY_INITIALIZATION            = "false"
      SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE   = "2"
      SPRING_DATASOURCE_HIKARI_MINIMUMIDLE       = "0"
      SPRING_DATASOURCE_HIKARI_CONNECTIONTIMEOUT = "20000"
      SPRING_DATASOURCE_HIKARI_IDLETIMEOUT       = "30000"
      SPRING_DATASOURCE_HIKARI_MAXLIFETIME       = "60000"
      SPRING_PROFILES_ACTIVE                     = "lambda"
      OTTERWORKS_REPORT_ASYNC_GENERATION_ENABLED = "false"
      ANALYTICS_SERVICE_URL                      = var.analytics_service_url
      AUDIT_SERVICE_URL                          = var.audit_service_url
      AUTH_SERVICE_URL                           = var.auth_service_url
    }
  }

  tags = {
    Namespace = var.namespace
  }

  depends_on = [
    aws_db_proxy_target.report,
    aws_iam_role_policy.lambda_runtime,
    aws_s3_object.lambda_artifact,
  ]
}

resource "aws_lambda_alias" "report" {
  name             = "live"
  description      = "Traffic alias for report-service ${var.namespace}"
  function_name    = aws_lambda_function.report.function_name
  function_version = aws_lambda_function.report.version
}

resource "aws_lambda_provisioned_concurrency_config" "report" {
  count = var.lambda_provisioned_concurrency > 0 ? 1 : 0

  function_name                     = aws_lambda_function.report.function_name
  qualifier                         = aws_lambda_alias.report.name
  provisioned_concurrent_executions = var.lambda_provisioned_concurrency
}

resource "aws_apigatewayv2_api" "report" {
  name          = "report-service-${var.namespace}"
  protocol_type = "HTTP"

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_apigatewayv2_integration" "report" {
  api_id                 = aws_apigatewayv2_api.report.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.report.invoke_arn
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.report.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.report.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.report.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      integrationError = "$context.integrationErrorMessage"
      responseLatency  = "$context.responseLatency"
    })
  }

  tags = {
    Namespace = var.namespace
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke-${var.namespace}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report.function_name
  qualifier     = aws_lambda_alias.report.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.report.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_metric_filter" "cold_start" {
  name           = "report-service-${var.namespace}-cold-start"
  pattern        = "\"Init Duration\""
  log_group_name = aws_cloudwatch_log_group.lambda.name

  metric_transformation {
    name      = "ColdStarts"
    namespace = "OtterWorks/ReportLambda/${var.namespace}"
    value     = "1"
  }
}

resource "aws_cloudwatch_dashboard" "report" {
  dashboard_name = "report-service-${var.namespace}"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Invocations, errors, and throttles"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.report.function_name],
            [".", "Errors", ".", "."],
            [".", "Throttles", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Duration"
          region = var.aws_region
          period = 60
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.report.function_name, { stat = "Average" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.report.function_name, { stat = "p95" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.report.function_name, { stat = "Maximum" }],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Concurrency"
          region = var.aws_region
          period = 60
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.report.function_name, { stat = "Maximum" }],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Cold starts"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["OtterWorks/ReportLambda/${var.namespace}", "ColdStarts"],
          ]
        }
      },
    ]
  })
}
