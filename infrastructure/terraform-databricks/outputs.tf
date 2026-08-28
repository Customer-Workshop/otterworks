output "warehouse_id" {
  description = "ID of the parent-owned serverless SQL warehouse."
  value       = data.databricks_sql_warehouse.shared.id
}

output "catalog" {
  description = "Name of the parent-owned Unity Catalog catalog."
  value       = data.databricks_catalog.shared.name
}

output "notebook_root" {
  description = "Parent-owned workspace root for migration notebooks."
  value       = var.notebook_root
}

output "landing_path" {
  description = "Parent-owned managed volume landing path."
  value       = var.landing_path
}

output "namespace" {
  description = "Namespace for this migration run."
  value       = var.ns
}
