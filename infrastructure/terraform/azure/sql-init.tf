# Post-apply T-SQL: apply migration/target/sql/*.sql (idempotent), create the reader login used by
# the Container Apps, and grant the user-assigned identity db_datareader/db_datawriter/db_ddladmin
# (CREATE USER ... FROM EXTERNAL PROVIDER, which requires the Entra admin set on the server).
#
# ldm init applies the same DDL, so this step is a convenience that makes the schemas exist right
# after terraform apply. It is skipped when apply_target_sql = false or in private mode (the machine
# running Terraform cannot reach the private endpoint); run scripts/apply-sql.sh from inside the
# VNet in that case, or rely on ldm init.

locals {
  run_sql_init = var.apply_target_sql && !var.private_networking
}

resource "null_resource" "sql_init" {
  count = local.run_sql_init ? 1 : 0

  triggers = {
    database_id   = azurerm_mssql_database.this.id
    ddl_hash      = local.target_sql_hash
    identity_name = azurerm_user_assigned_identity.this.name
    reader_login  = local.sql_reader_login
    # Rotating either password must re-run the script; only a digest lands in state/plan.
    reader_pw_digest = nonsensitive(sha256(random_password.sql_reader.result))
    admin_pw_digest  = nonsensitive(sha256(random_password.sql_admin.result))
  }

  provisioner "local-exec" {
    interpreter = ["/usr/bin/env", "bash", "-c"]
    command     = "${path.module}/scripts/apply-sql.sh"
    environment = {
      SQL_SERVER_FQDN     = local.sql_server_fqdn
      SQL_DATABASE        = azurerm_mssql_database.this.name
      SQL_ADMIN_USER      = local.sql_admin_login
      SQL_ADMIN_PASSWORD  = random_password.sql_admin.result
      SQL_READER_USER     = local.sql_reader_login
      SQL_READER_PASSWORD = random_password.sql_reader.result
      IDENTITY_NAME       = azurerm_user_assigned_identity.this.name
      IDENTITY_CLIENT_ID  = azurerm_user_assigned_identity.this.client_id
      DDL_DIR             = abspath(local.target_sql_dir)
      # Entra service-principal auth for the external-provider user; the secret comes from ARM_CLIENT_SECRET.
      AAD_CLIENT_ID = data.azurerm_client_config.current.client_id
      AAD_TENANT_ID = data.azurerm_client_config.current.tenant_id
    }
  }

  depends_on = [
    azurerm_mssql_firewall_rule.cidrs,
    azurerm_mssql_firewall_rule.azure_services,
  ]
}
