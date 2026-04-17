output "rds_endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_arn" {
  description = "ARN of the RDS PostgreSQL instance"
  value       = aws_db_instance.postgres.arn
}

output "file_metadata_table_name" {
  description = "DynamoDB table name for file metadata"
  value       = aws_dynamodb_table.file_metadata.name
}

output "file_metadata_table_arn" {
  description = "DynamoDB table ARN for file metadata"
  value       = aws_dynamodb_table.file_metadata.arn
}

output "audit_events_table_name" {
  description = "DynamoDB table name for audit events"
  value       = aws_dynamodb_table.audit_events.name
}

output "audit_events_table_arn" {
  description = "DynamoDB table ARN for audit events"
  value       = aws_dynamodb_table.audit_events.arn
}

output "notifications_table_name" {
  description = "DynamoDB table name for notifications"
  value       = aws_dynamodb_table.notifications.name
}

output "notifications_table_arn" {
  description = "DynamoDB table ARN for notifications"
  value       = aws_dynamodb_table.notifications.arn
}
