terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "lambda" {
  name        = "report-service-lambda-${var.namespace}"
  description = "Lambda security group for report-service ${var.namespace}"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "proxy" {
  name        = "report-service-proxy-${var.namespace}"
  description = "RDS Proxy security group for report-service ${var.namespace}"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "report-service-rds-${var.namespace}"
  description = "RDS security group for report-service ${var.namespace}"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id, aws_security_group.proxy.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "report" {
  name       = "report-service-${var.namespace}"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "report" {
  identifier             = "report-service-${var.namespace}"
  engine                 = "postgres"
  engine_version         = "15.18"
  instance_class         = "db.t4g.small"
  allocated_storage      = 20
  db_name                = var.db_name
  username               = var.db_user
  password               = var.db_password
  publicly_accessible    = false
  apply_immediately      = true
  skip_final_snapshot    = true
  deletion_protection    = false
  db_subnet_group_name   = aws_db_subnet_group.report.name
  vpc_security_group_ids = [aws_security_group.rds.id]
}

resource "aws_secretsmanager_secret" "report_db" {
  name                    = "report-service-${var.namespace}-db"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "report_db" {
  secret_id = aws_secretsmanager_secret.report_db.id
  secret_string = jsonencode({
    username = var.db_user
    password = var.db_password
  })
}

data "aws_iam_policy_document" "proxy_assume_role" {
  statement {
    effect = "Allow"

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
}

data "aws_iam_policy_document" "proxy_secret_access" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.report_db.arn]
  }
}

resource "aws_iam_role_policy" "proxy_secret_access" {
  name   = "read-report-db-secret"
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
  vpc_subnet_ids         = data.aws_subnets.default.ids

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.report_db.arn
  }

  depends_on = [aws_secretsmanager_secret_version.report_db]
}

resource "aws_db_proxy_default_target_group" "report" {
  db_proxy_name = aws_db_proxy.report.name
}

resource "aws_db_proxy_target" "report" {
  db_proxy_name          = aws_db_proxy.report.name
  target_group_name      = aws_db_proxy_default_target_group.report.name
  db_instance_identifier = aws_db_instance.report.identifier
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

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
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/report-service-${var.namespace}"
  retention_in_days = 7
}

resource "aws_s3_bucket" "lambda_artifact" {
  bucket        = "report-service-${var.namespace}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "lambda_artifact" {
  bucket = aws_s3_bucket.lambda_artifact.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
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
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DB_HOST                                    = aws_db_proxy.report.endpoint
      DB_PORT                                    = "5432"
      DB_NAME                                    = var.db_name
      DB_USER                                    = var.db_user
      DB_PASSWORD                                = var.db_password
      SPRING_DATASOURCE_URL                      = "jdbc:postgresql://${aws_db_proxy.report.endpoint}:5432/${var.db_name}"
      SPRING_DATASOURCE_USERNAME                 = var.db_user
      SPRING_DATASOURCE_PASSWORD                 = var.db_password
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
      LAMBDA_DEPLOYMENT_REVISION                 = "hikari-idle-timeout-30000"
      OTTERWORKS_REPORT_ASYNC_GENERATION_ENABLED = "false"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_vpc,
    aws_s3_object.lambda_artifact
  ]
}

resource "aws_lambda_alias" "report" {
  name             = "live"
  description      = "Warm production alias for report-service ${var.namespace}"
  function_name    = aws_lambda_function.report.function_name
  function_version = aws_lambda_function.report.version
}

resource "aws_lambda_provisioned_concurrency_config" "report" {
  function_name                     = aws_lambda_function.report.function_name
  qualifier                         = aws_lambda_alias.report.name
  provisioned_concurrent_executions = var.lambda_provisioned_concurrency
}

resource "aws_apigatewayv2_api" "report" {
  name          = "report-service-${var.namespace}"
  protocol_type = "HTTP"
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
}

resource "aws_lambda_permission" "apigateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report.function_name
  qualifier     = aws_lambda_alias.report.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.report.execution_arn}/*/*"
}
