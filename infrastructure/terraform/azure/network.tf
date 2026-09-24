# Optional private networking (var.private_networking = true):
# VNet with a delegated subnet for the Container Apps environment and a subnet for private
# endpoints; private endpoints + private DNS zones for SQL, blob storage and Key Vault;
# public network access is disabled on all three (main.tf).

locals {
  private_endpoints = var.private_networking ? {
    sql = {
      resource_id = azurerm_mssql_server.this.id
      subresource = "sqlServer"
      dns_zone    = "privatelink.database.windows.net"
    }
    blob = {
      resource_id = azurerm_storage_account.staging.id
      subresource = "blob"
      dns_zone    = "privatelink.blob.core.windows.net"
    }
    vault = {
      resource_id = azurerm_key_vault.this.id
      subresource = "vault"
      dns_zone    = "privatelink.vaultcore.azure.net"
    }
  } : {}
}

resource "azurerm_virtual_network" "this" {
  count = var.private_networking ? 1 : 0

  name                = local.vnet_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = [var.vnet_address_space]
  tags                = local.tags
}

resource "azurerm_subnet" "container_apps" {
  count = var.private_networking ? 1 : 0

  name                 = "snet-containerapps"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 7, 0)] # /23

  delegation {
    name = "containerapps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  count = var.private_networking ? 1 : 0

  name                 = "snet-private-endpoints"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 8, 2)] # /24
}

resource "azurerm_private_dns_zone" "zones" {
  for_each = local.private_endpoints

  name                = each.value.dns_zone
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "zones" {
  for_each = local.private_endpoints

  name                  = "${each.key}-${local.ns}"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.zones[each.key].name
  virtual_network_id    = azurerm_virtual_network.this[0].id
  tags                  = local.tags
}

resource "azurerm_private_endpoint" "endpoints" {
  for_each = local.private_endpoints

  name                = "pe-${each.key}-${local.ns}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints[0].id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-${each.key}-${local.ns}"
    private_connection_resource_id = each.value.resource_id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones[each.key].id]
  }
}
