resource "aws_kms_key" "projects" {
  description             = "SSE for the ${var.table_name} DynamoDB table"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  tags = {
    Name = "${var.table_name}-sse"
  }
}

resource "aws_kms_alias" "projects" {
  name          = "alias/${var.table_name}-sse"
  target_key_id = aws_kms_key.projects.key_id
}

# Single-table store for projects, tickets, comments, activity events and
# outbound delivery records. Small, low-traffic; on-demand billing.
resource "aws_dynamodb_table" "projects" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.projects.arn
  }

  tags = {
    Name = var.table_name
  }
}
