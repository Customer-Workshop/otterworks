output "glue_database_name" {
  description = "Glue Data Catalog database backing the Iceberg lakehouse."
  value       = aws_glue_catalog_database.analytics.name
}

output "events_table_name" {
  description = "Iceberg events table name."
  value       = aws_glue_catalog_table.analytics_events.name
}

output "warehouse_location" {
  description = "S3 URI of the Iceberg warehouse root."
  value       = local.warehouse_s3
}

output "table_location" {
  description = "S3 URI of the Iceberg events table."
  value       = local.table_location
}

output "athena_workgroup" {
  description = "Athena workgroup for querying the lakehouse."
  value       = aws_athena_workgroup.analytics.name
}

output "athena_results_bucket" {
  description = "S3 bucket for Athena query results."
  value       = aws_s3_bucket.athena_results.id
}

output "athena_output_location" {
  description = "S3 URI where Athena writes query results."
  value       = local.athena_results
}

output "iam_policy_arn" {
  description = "ARN of the least-privilege lakehouse IAM policy (attach to the analytics-service role)."
  value       = aws_iam_policy.lakehouse.arn
}
