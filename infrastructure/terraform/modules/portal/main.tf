# ------------------------------------------------------------------------------
# OtterWorks Infrastructure - Extracted Portal Services
# One PostgreSQL 16 database per bounded context extracted from legacy-portal.
#
# The monolith owned all three contexts in one schema; the extraction gave each service its
# own database (docs/migration/data-seams.md), and that boundary is the reason a bad release
# of one context cannot corrupt another. Sharing the estate's `otterworks` instance would put
# the boundary back at the schema level, so each context gets its own instance here.
#
# These databases are private: the services reach them from inside the VPC and nothing else
# does. No IRSA role is issued for the extracted services (they call no AWS API), and nothing
# in this module is created from Kubernetes (AGENTS.md).
# ------------------------------------------------------------------------------

locals {
  common_tags = {
    Module  = "portal"
    Project = var.project
  }

  # Fixed by the contracts (docs/migration/contracts/README.md) and by each service's
  # Flyway-owned schema. The keys are the context names used everywhere else in the
  # migration: Compose profile, Helm release, ECR repository, parity scenario file.
  contexts = {
    announcements = {
      db_name  = "announcements"
      username = "announcements"
    }
    user-preferences = {
      db_name  = "user_preferences"
      username = "user_preferences"
    }
    feedback = {
      db_name  = "feedback"
      username = "feedback"
    }
  }
}

resource "aws_db_subnet_group" "portal" {
  name       = "${var.project}-portal-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = merge(local.common_tags, {
    Name = "${var.project}-portal-${var.environment}"
  })
}

# One security group for all three, allowing PostgreSQL from inside the VPC only. The
# services are ClusterIP-only pods on the cluster's VPC; nothing outside it may connect.
resource "aws_security_group" "portal_db" {
  name        = "${var.project}-portal-db-${var.environment}"
  description = "PostgreSQL access for the extracted portal services"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from within the VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-portal-db-${var.environment}"
  })
}

resource "aws_db_instance" "portal" {
  for_each = local.contexts

  identifier = "${var.project}-${each.key}-${var.environment}"
  engine     = "postgres"
  # 16, matching docker-compose.portal.yml. The estate's shared instance is still on 15;
  # the extracted services were written and parity-proven against 16.
  engine_version = var.engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true

  db_name  = each.value.db_name
  username = each.value.username
  password = var.db_passwords[each.key]

  db_subnet_group_name   = aws_db_subnet_group.portal.name
  vpc_security_group_ids = [aws_security_group.portal_db.id]

  skip_final_snapshot = var.environment == "dev"
  deletion_protection = var.environment != "dev"

  # Decommission step 3 and pre-condition 5 (docs/migration/decommission.md) both depend on
  # a restorable copy of each extracted database existing, so backups are not optional even
  # in dev.
  backup_retention_period = var.environment == "dev" ? 1 : 14

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = merge(local.common_tags, {
    Service = "${each.key}-service"
    Context = each.key
  })
}
