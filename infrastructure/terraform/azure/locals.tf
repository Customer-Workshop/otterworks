data "azurerm_client_config" "current" {}

# Public IP of the machine running Terraform, used only for the optional SQL firewall rule that
# lets apply_target_sql reach the database. Skipped when deployer_cidrs is set or in private mode.
data "http" "deployer_ip" {
  count = var.apply_target_sql && !var.private_networking && length(var.deployer_cidrs) == 0 ? 1 : 0
  url   = "https://api.ipify.org?format=text"
}

locals {
  ns          = var.namespace
  ns_compact  = replace(var.namespace, "-", "")
  sub_hash    = md5(data.azurerm_client_config.current.subscription_id)
  name_suffix = substr(local.sub_hash, 0, 3)

  tags = {
    namespace = var.namespace
    owner     = var.owner
    demo      = "legacy-data-migration"
    expires   = var.expires
    run_token = var.run_token
    state     = var.state
  }

  # Derived names (CONTRACTS.md §3.2).
  resource_group_name  = "rg-otterworks-${local.ns}"
  sql_server_name      = "sql-otterworks-${local.ns}"
  sql_database_name    = "sqldb-otterworks-${local.ns}"
  storage_account_name = substr("stow${local.ns_compact}${local.name_suffix}", 0, 24)
  staging_container    = "staging-${local.ns}"
  key_vault_name       = substr("kvow${local.ns_compact}${substr(local.sub_hash, 0, 2)}", 0, 24)
  identity_name        = "id-otterworks-${local.ns}"
  cae_name             = "cae-otterworks-${local.ns}"
  law_name             = "log-otterworks-${local.ns}"
  report_app_name      = "ca-report-${local.ns}"
  audit_app_name       = "ca-audit-${local.ns}"
  job_name             = "caj-ldm-${local.ns}"
  vnet_name            = "vnet-otterworks-${local.ns}"

  sql_admin_login  = "ldmadmin"
  sql_reader_login = "ldmreader"

  sql_server_fqdn = azurerm_mssql_server.this.fully_qualified_domain_name

  deployer_cidrs = var.private_networking || !var.apply_target_sql ? [] : (
    length(var.deployer_cidrs) > 0 ? var.deployer_cidrs : ["${trimspace(data.http.deployer_ip[0].response_body)}/32"]
  )

  firewall_rules = merge(
    { for i, c in var.eks_egress_cidrs : "eks-egress-${i}" => c },
    { for i, c in local.deployer_cidrs : "deployer-${i}" => c },
  )

  # Environment shared by the Container Apps and the job (CONTRACTS.md §9.2 / §10.4).
  azsql_env = {
    AZSQL_SERVER   = local.sql_server_fqdn
    AZSQL_DATABASE = local.sql_database_name
    AZSQL_AUTH     = "sql"
    LDM_NAMESPACE  = var.namespace
  }

  target_sql_dir   = "${path.module}/../../../migration/target/sql"
  target_sql_files = fileset(local.target_sql_dir, "*.sql")
  target_sql_hash  = sha256(join("", [for f in sort(tolist(local.target_sql_files)) : filesha256("${local.target_sql_dir}/${f}")]))
}

# Mirror the contract check "namespace == run_token-state" and the egress-CIDR rule.
resource "terraform_data" "contract_checks" {
  lifecycle {
    precondition {
      condition     = var.namespace == "${var.run_token}-${var.state}"
      error_message = "namespace must equal \"${var.run_token}-${var.state}\"."
    }
    precondition {
      condition     = var.private_networking || length(var.eks_egress_cidrs) > 0
      error_message = "eks_egress_cidrs may be empty only when private_networking is true."
    }
  }
}
