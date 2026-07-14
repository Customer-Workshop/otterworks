# ------------------------------------------------------------------------------
# OtterWorks Aurora Serverless v2 Module (namespace: aur1)
#
# REPLATFORM target for the self-managed RDS PostgreSQL data layer
# (auth/document/admin/report/analytics). This module lives ALONGSIDE
# modules/database (the RDS before-state) and never replaces or modifies it.
#
# Every resource carries the ${var.namespace} suffix so concurrent sibling
# migrations and repeated runs never collide. Revert is a single:
#   terraform destroy -target=module.aurora_aur1
# ------------------------------------------------------------------------------

locals {
  ns          = var.namespace
  name_prefix = "${var.project}-aurora-${local.ns}"

  common_tags = {
    Module    = "aurora-${local.ns}"
    Project   = var.project
    Namespace = local.ns
    Migration = "postgres-aurora-${local.ns}"
  }
}

# --- Aurora Subnet Group (namespaced, alongside the RDS subnet group) ---

resource "aws_db_subnet_group" "aurora" {
  name       = "${local.name_prefix}-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = merge(local.common_tags, {
    Service = "shared-database-aurora"
  })
}

# --- Aurora Security Group (namespaced, own SG so RDS SG is untouched) ---

resource "aws_security_group" "aurora" {
  name        = "${local.name_prefix}-sg-${var.environment}"
  description = "Security group for OtterWorks Aurora Serverless v2 (namespace ${local.ns})"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
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
    Service = "shared-database-aurora"
  })
}

# --- Aurora Serverless v2 Cluster (scale-to-zero) ---

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = "${local.name_prefix}-${var.environment}"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned" # Serverless v2 runs on the provisioned engine mode
  engine_version     = var.engine_version

  # Same database name / master user as the RDS before-state: a
  # connection-layer-only swap must find an identical logical database.
  database_name   = "otterworks"
  master_username = "otterworks_admin"
  master_password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  storage_encrypted = true

  # IAM database authentication so services can connect with least-privilege
  # short-lived tokens (see aws_iam_policy.rds_connect) instead of a static
  # password where desired. Password auth remains available for parity.
  iam_database_authentication_enabled = true

  serverlessv2_scaling_configuration {
    min_capacity             = var.min_capacity
    max_capacity             = var.max_capacity
    seconds_until_auto_pause = var.min_capacity == 0 ? var.seconds_until_auto_pause : null
  }

  skip_final_snapshot = var.environment == "dev"
  deletion_protection = var.environment != "dev"

  backup_retention_period = var.environment == "dev" ? 1 : 7

  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = merge(local.common_tags, {
    Service = "shared-database-aurora"
  })
}

resource "aws_rds_cluster_instance" "aurora" {
  identifier         = "${local.name_prefix}-instance-${var.environment}"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  db_subnet_group_name = aws_db_subnet_group.aurora.name

  performance_insights_enabled = var.environment != "dev"

  tags = merge(local.common_tags, {
    Service = "shared-database-aurora"
  })
}

# --- Least-privilege IAM: rds-db:connect scoped to this cluster only ---
# Self-contained in the module (does NOT touch the shared IRSA block in main.tf).
# Attach to a SQL-service IRSA role to grant IAM-auth DB access to Aurora only.

data "aws_caller_identity" "current" {}

resource "aws_iam_policy" "rds_connect" {
  name        = "${local.name_prefix}-rds-connect-${var.environment}"
  description = "Least-privilege rds-db:connect to the Aurora ${local.ns} cluster (namespace ${local.ns})"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["rds-db:connect"]
        Resource = [
          "arn:aws:rds-db:*:${data.aws_caller_identity.current.account_id}:dbuser:${aws_rds_cluster.aurora.cluster_resource_id}/otterworks_admin",
        ]
      },
    ]
  })

  tags = local.common_tags
}
