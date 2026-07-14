output "bucket_name" {
  value = aws_s3_bucket.lakehouse.id
}

output "bucket_arn" {
  value = aws_s3_bucket.lakehouse.arn
}

output "database_name" {
  value = aws_glue_catalog_database.lakehouse.name
}

output "database_arn" {
  value = aws_glue_catalog_database.lakehouse.arn
}

output "events_table_name" {
  value = local.events_table
}

output "aggregates_table_name" {
  value = local.aggregates_table
}

output "table_arns" {
  value = [
    "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.database_name}/${local.events_table}",
    "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.database_name}/${local.aggregates_table}",
  ]
}

output "glue_catalog_arn" {
  value = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog"
}

output "athena_workgroup_name" {
  value = aws_athena_workgroup.lakehouse.name
}

output "athena_workgroup_arn" {
  value = aws_athena_workgroup.lakehouse.arn
}

output "athena_output" {
  value = local.query_output
}

output "warehouse" {
  value = local.warehouse
}

output "analytics_access_policy_arn" {
  value = aws_iam_policy.analytics_access.arn
}
