# Container Apps environment, the Azure-facing report/audit apps and the manual migration job.

resource "azurerm_container_app_environment" "this" {
  name                       = local.cae_name
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = local.tags

  infrastructure_subnet_id       = var.private_networking ? azurerm_subnet.container_apps[0].id : null
  internal_load_balancer_enabled = var.private_networking ? true : null

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

locals {
  # Env shared by the two apps: contract §10.4 (reader credential from Key Vault).
  # The Azure copies have no Postgres/DynamoDB beside them: they serve only the archive read
  # path, so Spring must not touch its JDBC datasource at boot and the probes hit
  # /health/archive (pings Azure SQL) instead of the AWS-backed /health.
  app_env = merge(local.azsql_env, {
    ARCHIVE_STORE                                                   = "azuresql"
    LDM_SESSION_LINKS                                               = var.session_links_json
    SPRING_JPA_HIBERNATE_DDL_AUTO                                   = "none"
    SPRING_JPA_PROPERTIES_HIBERNATE_TEMP_USE_JDBC_METADATA_DEFAULTS = "false"
    SPRING_DATASOURCE_HIKARI_INITIALIZATION_FAIL_TIMEOUT            = "-1"
  })
  app_probe_path = "/health/archive"

  app_secret_env = {
    AZSQL_USER     = "azsql-reader-user"
    AZSQL_PASSWORD = "azsql-reader-password"
  }

  apps = {
    report = { name = local.report_app_name, image = var.report_image, port = 8091 }
    audit  = { name = local.audit_app_name, image = var.audit_image, port = 8090 }
  }

  # Key Vault secrets exposed to the apps and the job (name -> secret id without version).
  kv_secret_refs = {
    for k, s in azurerm_key_vault_secret.secrets : k => s.versionless_id
  }
}

resource "azurerm_container_app" "apps" {
  for_each = local.apps

  name                         = each.value.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  registry {
    server               = var.registry_server
    username             = var.registry_username
    password_secret_name = "registry-password"
  }

  secret {
    name  = "registry-password"
    value = var.registry_password
  }

  dynamic "secret" {
    for_each = local.app_secret_env
    content {
      name                = secret.value
      key_vault_secret_id = local.kv_secret_refs[secret.value]
      identity            = azurerm_user_assigned_identity.this.id
    }
  }

  ingress {
    external_enabled = true
    target_port      = each.value.port
    transport        = "auto"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = each.key
      image  = each.value.image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.app_secret_env
        content {
          name        = env.key
          secret_name = env.value
        }
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = each.value.port
        path                    = local.app_probe_path
        initial_delay           = 30
        timeout                 = 10
        failure_count_threshold = 6
      }
      readiness_probe {
        transport               = "HTTP"
        port                    = each.value.port
        path                    = local.app_probe_path
        timeout                 = 10
        failure_count_threshold = 6
      }
    }
  }

  depends_on = [azurerm_role_assignment.identity_kv_secrets_user]
}

locals {
  job_env = merge(local.azsql_env, {
    AZ_STORAGE_ACCOUNT   = azurerm_storage_account.staging.name
    AZ_STAGING_CONTAINER = azurerm_storage_container.staging.name
    LOCAL_STAGING_DIR    = "/work/staging"
    LDM_HOST             = "aca"
    LDM_JOB_IMAGE        = var.job_image
    LDM_RUN_IN_AZURE     = tostring(var.run_job_in_azure)
    LDM_SESSION_LINKS    = var.session_links_json
    AZURE_CLIENT_ID      = azurerm_user_assigned_identity.this.client_id
  })

  job_secret_env = {
    AZSQL_USER     = "azsql-admin-user"
    AZSQL_PASSWORD = "azsql-admin-password"
    AZ_STORAGE_KEY = "staging-storage-key"
  }
}

resource "azurerm_container_app_job" "ldm" {
  name                         = local.job_name
  location                     = azurerm_resource_group.this.location
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 3600
  replica_retry_limit          = 0
  tags                         = merge(local.tags, { run_job_in_azure = tostring(var.run_job_in_azure) })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  registry {
    server               = var.registry_server
    username             = var.registry_username
    password_secret_name = "registry-password"
  }

  secret {
    name  = "registry-password"
    value = var.registry_password
  }

  dynamic "secret" {
    for_each = local.job_secret_env
    content {
      name                = secret.value
      key_vault_secret_id = local.kv_secret_refs[secret.value]
      identity            = azurerm_user_assigned_identity.this.id
    }
  }

  template {
    container {
      name   = "ldm"
      image  = var.job_image
      cpu    = 1.0
      memory = "2Gi"
      # Stage and run id are supplied at start time:
      #   az containerapp job start -n caj-ldm-<NS> -g rg-otterworks-<NS> \
      #     --args load --manifest /app/migration/manifest.yaml --namespace <NS> --run-id <id>
      args = ["reconcile", "--manifest", "/app/migration/manifest.yaml", "--namespace", var.namespace, "--run-id", "unset"]

      dynamic "env" {
        for_each = local.job_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.job_secret_env
        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.identity_kv_secrets_user]
}
