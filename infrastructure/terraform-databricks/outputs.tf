output "catalog" {
  value = databricks_catalog.ow_tp.name
}

output "volume_path" {
  value = "/Volumes/${databricks_catalog.ow_tp.name}/${databricks_schema.ow_tp_bronze.name}/${databricks_volume.ow_tp_bronze_landing.name}"
}

output "job_id" {
  value = databricks_job.ow_tp_custbill.id
}
