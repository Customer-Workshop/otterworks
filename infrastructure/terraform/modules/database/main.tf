# RDS PostgreSQL and DynamoDB tables for OtterWorks

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project}-postgres-${var.environment}"
  engine         = "postgres"
  engine_version = "15.5"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_encrypted     = true

  db_name  = "otterworks"
  username = "otterworks_admin"
  password = var.db_password

  skip_final_snapshot = var.environment == "dev"
  deletion_protection = var.environment != "dev"

  backup_retention_period = var.environment == "dev" ? 1 : 7

  tags = {
    Service = "shared-database"
  }
}

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

  tags = {
    Service = "file-service"
  }
}

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

  tags = {
    Service = "audit-service"
  }
}

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

  tags = {
    Service = "notification-service"
  }
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

variable "environment" { type = string }
variable "project" { type = string }
variable "db_password" {
  type      = string
  sensitive = true
}
