# Customer-managed KMS key for the control table (SSE). Rotation on; the table
# holds durable tenant/lock/audit state so a managed key is worth the ~$1/mo.
resource "aws_kms_key" "control" {
  description             = "SSE for the ${var.control_table_name} DynamoDB control table"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  tags = {
    Name = "${var.control_table_name}-sse"
  }
}

resource "aws_kms_alias" "control" {
  name          = "alias/${var.control_table_name}-sse"
  target_key_id = aws_kms_key.control.key_id
}

# Durable control-plane state store. Independent of any ephemeral tenant:
# tenant teardown / node churn / cluster loss never affects this table.
resource "aws_dynamodb_table" "control" {
  name         = var.control_table_name
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

  # DynamoDB TTL on lock items + informational tenant expiry.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.control.arn
  }

  deletion_protection_enabled = true

  tags = {
    Name = var.control_table_name
  }
}
