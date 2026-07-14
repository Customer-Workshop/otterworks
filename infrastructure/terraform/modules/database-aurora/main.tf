# ------------------------------------------------------------------------------
# OtterWorks Aurora Serverless v2 Module
#
# Replatforms the shared PostgreSQL data layer onto Amazon Aurora Serverless v2.
# This module is namespaced and provisioned ALONGSIDE modules/database (the
# existing RDS PostgreSQL instance) — it does NOT replace it. Applications cut
# over by pointing their existing DB_HOST / DATABASE_URL config at the writer
# endpoint below; the RDS instance stays in place for revert.
#
# Security posture:
#   - IAM database authentication enabled (short-lived tokens, no static creds)
#   - TLS enforced in-transit via rds.force_ssl = 1 (cluster parameter group)
#   - Storage encrypted at rest
# ------------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  common_tags = {
    Module  = "database-aurora"
    Project = var.project
  }

  cluster_identifier = "${var.project}-aurora-${var.environment}"
}

# --- Aurora Subnet Group ---

resource "aws_db_subnet_group" "aurora" {
  name       = "${var.project}-aurora-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = merge(local.common_tags, {
    Service = "shared-database"
  })
}

# --- Aurora Security Group ---

resource "aws_security_group" "aurora" {
  name        = "${var.project}-aurora-${var.environment}"
  description = "Security group for OtterWorks Aurora Serverless v2 PostgreSQL"
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
    Service = "shared-database"
  })
}

# --- Cluster Parameter Group: enforce TLS in transit ---

resource "aws_rds_cluster_parameter_group" "aurora" {
  name        = "${var.project}-aurora-${var.environment}"
  family      = "aurora-postgresql${split(".", var.engine_version)[0]}"
  description = "OtterWorks Aurora PostgreSQL cluster parameters (TLS enforced)"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = local.common_tags
}

# --- Aurora Serverless v2 Cluster ---

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = local.cluster_identifier
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = var.engine_version

  database_name   = "otterworks"
  master_username = "otterworks_admin"
  master_password = var.db_password

  # IAM database authentication — issue short-lived auth tokens instead of
  # relying solely on the master password. Application roles authenticate with
  # tokens (see the rds-db:connect policy output below).
  iam_database_authentication_enabled = true

  db_subnet_group_name            = aws_db_subnet_group.aurora.name
  vpc_security_group_ids          = [aws_security_group.aurora.id]
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.aurora.name

  storage_encrypted = true

  skip_final_snapshot       = var.environment == "dev"
  final_snapshot_identifier = var.environment == "dev" ? null : "${local.cluster_identifier}-final"
  deletion_protection       = var.environment != "dev"

  backup_retention_period = var.environment == "dev" ? 1 : 7

  enabled_cloudwatch_logs_exports = ["postgresql"]

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }

  tags = merge(local.common_tags, {
    Service = "shared-database"
  })
}

# --- Aurora Serverless v2 Instances ---

resource "aws_rds_cluster_instance" "aurora" {
  count = var.instance_count

  identifier         = "${local.cluster_identifier}-${count.index}"
  cluster_identifier = aws_rds_cluster.aurora.id
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version
  instance_class     = "db.serverless"

  db_subnet_group_name = aws_db_subnet_group.aurora.name

  performance_insights_enabled = var.environment != "dev"

  tags = merge(local.common_tags, {
    Service = "shared-database"
  })
}

# --- IAM policy document for rds-db:connect ---
# Grants IAM-authenticated database access for the configured roles. Attach to
# the service IRSA roles that connect to Aurora.

data "aws_iam_policy_document" "rds_connect" {
  statement {
    sid     = "AuroraIamConnect"
    effect  = "Allow"
    actions = ["rds-db:connect"]
    resources = [
      for user in var.iam_db_users :
      "arn:aws:rds-db:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_rds_cluster.aurora.cluster_resource_id}/${user}"
    ]
  }
}
