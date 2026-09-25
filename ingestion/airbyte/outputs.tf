output "landing_bucket" {
  value = aws_s3_bucket.landing.bucket
}

output "connection_id" {
  value = airbyte_connection.billing.connection_id
}

output "source_id" {
  value = airbyte_source_s3.billing_landing.source_id
}

output "destination_id" {
  value = airbyte_destination_databricks.lakehouse.destination_id
}

output "hashed_fields" {
  description = "Applied hashing mappers per stream, as TABLE=COL,COL specs for sync_and_recon.py --hashed-fields"
  value       = [for table, fields in var.hashed_fields : "${table}=${join(",", fields)}"]
}

output "hashed_field_suffix" {
  value = var.hashed_field_suffix
}

output "destination_schema" {
  value = "${var.databricks_catalog}.airbyte_${var.namespace}"
}
