# --- Storage ---

output "s3_file_bucket" {
  description = "S3 bucket for file storage"
  value       = module.storage.file_bucket_name
}

output "s3_data_lake_bucket" {
  description = "S3 bucket for analytics data lake"
  value       = module.storage.data_lake_bucket_name
}

output "s3_audit_archive_bucket" {
  description = "S3 bucket for audit archive"
  value       = module.storage.audit_archive_bucket_name
}

# --- Analytics Iceberg (ice1 migration namespace) ---

output "analytics_iceberg_ice1_bucket" {
  description = "Namespaced S3 bucket for the analytics Iceberg lakehouse"
  value       = module.analytics_iceberg_ice1.bucket_name
}

output "analytics_iceberg_ice1_database" {
  description = "Glue database for analytics Iceberg tables"
  value       = module.analytics_iceberg_ice1.database_name
}

output "analytics_iceberg_ice1_events_table" {
  description = "Raw analytics Iceberg events table"
  value       = module.analytics_iceberg_ice1.events_table_name
}

output "analytics_iceberg_ice1_aggregates_table" {
  description = "Analytics Iceberg daily aggregate table"
  value       = module.analytics_iceberg_ice1.aggregates_table_name
}

output "analytics_iceberg_ice1_athena_workgroup" {
  description = "Athena workgroup for the analytics Iceberg lakehouse"
  value       = module.analytics_iceberg_ice1.athena_workgroup_name
}

output "analytics_iceberg_ice1_athena_output" {
  description = "S3 URI for namespaced Athena query results"
  value       = module.analytics_iceberg_ice1.athena_output
}

output "analytics_iceberg_ice1_warehouse" {
  description = "S3 URI for analytics Iceberg table data"
  value       = module.analytics_iceberg_ice1.warehouse
}

# --- Database ---

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.rds_endpoint
}

output "dynamodb_file_metadata_table" {
  description = "DynamoDB table name for file metadata"
  value       = module.database.file_metadata_table_name
}

output "dynamodb_audit_events_table" {
  description = "DynamoDB table name for audit events"
  value       = module.database.audit_events_table_name
}

output "dynamodb_notifications_table" {
  description = "DynamoDB table name for notifications"
  value       = module.database.notifications_table_name
}

output "dynamodb_folders_table" {
  description = "DynamoDB table name for folders"
  value       = module.database.folders_table_name
}

output "dynamodb_file_versions_table" {
  description = "DynamoDB table name for file versions"
  value       = module.database.file_versions_table_name
}

output "dynamodb_file_shares_table" {
  description = "DynamoDB table name for file shares"
  value       = module.database.file_shares_table_name
}

# --- Messaging ---

output "sqs_notification_queue_url" {
  description = "SQS queue URL for notifications"
  value       = module.messaging.notification_queue_url
}

output "sns_events_topic_arn" {
  description = "SNS topic ARN for system events"
  value       = module.messaging.events_topic_arn
}

# --- Search ---

output "meilisearch_ecs_cluster_arn" {
  description = "MeiliSearch ECS cluster ARN"
  value       = module.search.meilisearch_ecs_cluster_arn
}

# --- Auth ---

output "cognito_user_pool_id" {
  description = "Cognito user pool ID"
  value       = module.auth.user_pool_id
}

output "cognito_web_client_id" {
  description = "Cognito web client ID"
  value       = module.auth.user_pool_client_id
}

output "cognito_admin_client_id" {
  description = "Cognito admin client ID"
  value       = module.auth.admin_client_id
}

# --- Cache ---

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.cache.redis_endpoint
}

# --- Monitoring ---

output "cloudwatch_log_groups" {
  description = "Map of service name to CloudWatch log group name"
  value       = module.monitoring.log_group_names
}

# --- IRSA ---

output "irsa_role_arns" {
  description = "Map of service account name to IAM role ARN"
  value       = module.irsa.role_arns
}
