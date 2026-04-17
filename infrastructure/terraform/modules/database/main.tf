# ------------------------------------------------------------------------------
# OtterWorks Database Module
# RDS PostgreSQL and DynamoDB tables
# ------------------------------------------------------------------------------

locals {
  common_tags = {
    Module  = "database"
    Project = var.project
  }
}

# --- RDS PostgreSQL ---

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project}-postgres-${var.environment}"
  engine         = "postgres"
  engine_version = "15.5"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true

  db_name  = "otterworks"
  username = "otterworks_admin"
  password = var.db_password

  skip_final_snapshot = var.environment == "dev"
  deletion_protection = var.environment != "dev"

  backup_retention_period = var.environment == "dev" ? 1 : 7

  tags = merge(local.common_tags, {
    Service = "shared-database"
  })
}

# --- DynamoDB: File Metadata ---

resource "aws_dynamodb_table" "file_metadata" {
  name         = "${var.project}-file-metadata-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "owner_id"
    type = "S"
  }

  attribute {
    name = "folder_id"
    type = "S"
  }

  global_secondary_index {
    name            = "owner-index"
    hash_key        = "owner_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "folder-index"
    hash_key        = "folder_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment != "dev"
  }

  tags = merge(local.common_tags, {
    Service = "file-service"
  })
}

# --- DynamoDB: Audit Events ---

resource "aws_dynamodb_table" "audit_events" {
  name         = "${var.project}-audit-events-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-index"
    hash_key        = "user_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "timestamp-index"
    hash_key        = "id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Service = "audit-service"
  })
}

# --- DynamoDB: Notifications ---

resource "aws_dynamodb_table" "notifications" {
  name         = "${var.project}-notifications-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment != "dev"
  }

  tags = merge(local.common_tags, {
    Service = "notification-service"
  })
}
