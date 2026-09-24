output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "sql_server_name" {
  value = azurerm_mssql_server.this.name
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.this.fully_qualified_domain_name
}

output "sql_database_name" {
  value = azurerm_mssql_database.this.name
}

output "key_vault_name" {
  value = azurerm_key_vault.this.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "storage_account_name" {
  value = azurerm_storage_account.staging.name
}

output "staging_container" {
  value = azurerm_storage_container.staging.name
}

output "managed_identity_client_id" {
  value = azurerm_user_assigned_identity.this.client_id
}

output "managed_identity_principal_id" {
  value = azurerm_user_assigned_identity.this.principal_id
}

output "container_app_env_id" {
  value = azurerm_container_app_environment.this.id
}

output "container_app_job_name" {
  value = azurerm_container_app_job.ldm.name
}

output "report_fqdn" {
  value = azurerm_container_app.apps["report"].ingress[0].fqdn
}

output "audit_fqdn" {
  value = azurerm_container_app.apps["audit"].ingress[0].fqdn
}

output "private_networking" {
  value = var.private_networking
}

output "tags" {
  value = local.tags
}
