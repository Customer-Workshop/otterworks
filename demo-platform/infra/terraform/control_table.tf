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

  deletion_protection_enabled = true

  tags = {
    Name = var.control_table_name
  }
}
