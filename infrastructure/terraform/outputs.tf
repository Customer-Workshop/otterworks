output "s3_file_bucket" {
  description = "S3 bucket for file storage"
  value       = module.storage.file_bucket_name
}

output "s3_data_lake_bucket" {
  description = "S3 bucket for analytics data lake"
  value       = module.storage.data_lake_bucket_name
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.rds_endpoint
}

output "sqs_notification_queue_url" {
  description = "SQS queue URL for notifications"
  value       = module.messaging.notification_queue_url
}

output "sns_events_topic_arn" {
  description = "SNS topic ARN for system events"
  value       = module.messaging.events_topic_arn
}

output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint"
  value       = module.search.opensearch_endpoint
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID"
  value       = module.auth.user_pool_id
}
