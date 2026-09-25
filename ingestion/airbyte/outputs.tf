output "landing_bucket" {
  value = aws_s3_bucket.landing.bucket
}

output "connection_id" {
  value = airbyte_connection.billing.connection_id
}

output "source_id" {
  value = airbyte_source_s3.billing_landing.source_id
}

output "custbill_connection_id" {
  value = airbyte_connection.custbill.connection_id
}

output "custbill_source_id" {
  value = airbyte_source_custom.custbill_fixedwidth.source_id
}

output "destination_id" {
  value = airbyte_destination_databricks.lakehouse.destination_id
}

output "destination_schema" {
  value = "${var.databricks_catalog}.airbyte_${var.namespace}"
}
