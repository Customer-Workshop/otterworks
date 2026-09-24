# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration: per-namespace Azure target (CONTRACTS.md §11).
# One root module, one state file per namespace token (<run>-<state>).
# Everything lives in rg-otterworks-<namespace> and carries local.tags.
# ------------------------------------------------------------------------------

resource "azurerm_resource_group" "this" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags

  depends_on = [terraform_data.contract_checks]
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = local.law_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# ---- identity ---------------------------------------------------------------

resource "azurerm_user_assigned_identity" "this" {
  name                = local.identity_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

# ---- storage ----------------------------------------------------------------

resource "azurerm_storage_account" "staging" {
  name                            = local.storage_account_name
  location                        = azurerm_resource_group.this.location
  resource_group_name             = azurerm_resource_group.this.name
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled      = true
  public_network_access_enabled   = !var.private_networking
  tags                            = local.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_container" "staging" {
  name                  = local.staging_container
  storage_account_id    = azurerm_storage_account.staging.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "identity_blob_reader" {
  count = var.manage_rbac ? 1 : 0

  scope                = azurerm_storage_container.staging.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

# ---- key vault --------------------------------------------------------------

resource "azurerm_key_vault" "this" {
  name                       = local.key_vault_name
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = var.manage_rbac
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  # Secrets are written over the data plane by the machine running apply, so in private mode the
  # vault keeps a public endpoint locked to the deployer CIDRs (plus the private endpoint).
  public_network_access_enabled = true
  tags                          = local.tags

  dynamic "network_acls" {
    for_each = var.private_networking ? [1] : []
    content {
      default_action = "Deny"
      bypass         = "AzureServices"
      ip_rules       = local.deployer_cidrs
    }
  }

  # Access-policy mode (manage_rbac=false): Contributor alone can grant these.
  dynamic "access_policy" {
    for_each = var.manage_rbac ? {} : {
      deployer = { object_id = data.azurerm_client_config.current.object_id, perms = ["Get", "List", "Set", "Delete", "Purge", "Recover"] }
      identity = { object_id = azurerm_user_assigned_identity.this.principal_id, perms = ["Get", "List"] }
    }
    content {
      tenant_id          = data.azurerm_client_config.current.tenant_id
      object_id          = access_policy.value.object_id
      secret_permissions = access_policy.value.perms
    }
  }
}

# RBAC mode (manage_rbac=true): the deploying principal writes the secrets; the identity reads them.
resource "azurerm_role_assignment" "deployer_kv_secrets_officer" {
  count = var.manage_rbac ? 1 : 0

  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "identity_kv_secrets_user" {
  count = var.manage_rbac ? 1 : 0

  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}

# RBAC propagation is eventually consistent; give the officer role a moment before writing secrets.
resource "time_sleep" "kv_rbac_propagation" {
  create_duration = var.manage_rbac ? "60s" : "1s"
  depends_on      = [azurerm_role_assignment.deployer_kv_secrets_officer, azurerm_key_vault.this]
}

resource "random_password" "sql_admin" {
  length           = 32
  special          = true
  override_special = "!#%^*-_+=?"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "random_password" "sql_reader" {
  length           = 32
  special          = true
  override_special = "!#%^*-_+=?"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "azurerm_key_vault_secret" "secrets" {
  for_each = {
    azsql-admin-user      = local.sql_admin_login
    azsql-admin-password  = random_password.sql_admin.result
    azsql-reader-user     = local.sql_reader_login
    azsql-reader-password = random_password.sql_reader.result
    staging-storage-key   = azurerm_storage_account.staging.primary_access_key
  }

  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.this.id
  content_type = "text/plain"
  tags         = local.tags

  depends_on = [time_sleep.kv_rbac_propagation]
}

# ---- azure sql --------------------------------------------------------------

resource "azurerm_mssql_server" "this" {
  name                          = local.sql_server_name
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  version                       = "12.0"
  administrator_login           = local.sql_admin_login
  administrator_login_password  = random_password.sql_admin.result
  minimum_tls_version           = "1.2"
  public_network_access_enabled = !var.private_networking
  tags                          = local.tags

  # Entra admin = the deploying service principal; needed for CREATE USER ... FROM EXTERNAL PROVIDER.
  azuread_administrator {
    login_username              = "sp-terraform-deployer"
    object_id                   = data.azurerm_client_config.current.object_id
    tenant_id                   = data.azurerm_client_config.current.tenant_id
    azuread_authentication_only = false
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }
  primary_user_assigned_identity_id = azurerm_user_assigned_identity.this.id
}

resource "azurerm_mssql_database" "this" {
  name                        = local.sql_database_name
  server_id                   = azurerm_mssql_server.this.id
  sku_name                    = "GP_S_Gen5_2"
  min_capacity                = 0.5
  auto_pause_delay_in_minutes = 60
  max_size_gb                 = 32
  zone_redundant              = false
  storage_account_type        = "Local"
  collation                   = "SQL_Latin1_General_CP1_CI_AS"
  tags                        = local.tags
}

resource "azurerm_mssql_firewall_rule" "cidrs" {
  for_each = var.private_networking ? {} : local.firewall_rules

  name             = each.key
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = cidrhost(each.value, 0)
  end_ip_address   = cidrhost(each.value, -1)
}

# 0.0.0.0-0.0.0.0 is Azure's "allow Azure services" sentinel; it lets the Container Apps job reach the server.
resource "azurerm_mssql_firewall_rule" "azure_services" {
  count = var.private_networking ? 0 : 1

  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
