# ------------------------------------------------------------------------------
# OtterWorks Search Module
# MeiliSearch instance for full-text search
# ------------------------------------------------------------------------------

locals {
  common_tags = {
    Module  = "search"
    Project = var.project
  }
}

# --- MeiliSearch Security Group ---

resource "aws_security_group" "meilisearch" {
  name        = "${var.project}-meilisearch-${var.environment}"
  description = "Security group for OtterWorks MeiliSearch"
  vpc_id      = var.vpc_id

  ingress {
    description = "MeiliSearch HTTP from VPC"
    from_port   = 7700
    to_port     = 7700
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}

# --- ECS Cluster ---

resource "aws_ecs_cluster" "meilisearch" {
  name = "${var.project}-meilisearch-${var.environment}"

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}

# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "meilisearch" {
  name              = "/ecs/${var.project}-meilisearch-${var.environment}"
  retention_in_days = 30

  tags = local.common_tags
}

# --- ECS Task Definition ---

resource "aws_ecs_task_definition" "meilisearch" {
  family                   = "${var.project}-meilisearch-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.meilisearch_cpu
  memory                   = var.meilisearch_memory
  execution_role_arn       = var.ecs_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "meilisearch"
      image     = "getmeili/meilisearch:v1.6"
      essential = true
      portMappings = [
        {
          containerPort = 7700
          hostPort      = 7700
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "MEILI_ENV", value = var.environment == "prod" ? "production" : "development" },
        { name = "MEILI_NO_ANALYTICS", value = "true" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.meilisearch.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "meilisearch"
        }
      }
    }
  ])

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}

data "aws_region" "current" {}

# --- ECS Service ---

resource "aws_ecs_service" "meilisearch" {
  name            = "${var.project}-meilisearch-${var.environment}"
  cluster         = aws_ecs_cluster.meilisearch.id
  task_definition = aws_ecs_task_definition.meilisearch.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.meilisearch.id]
    assign_public_ip = false
  }

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}
