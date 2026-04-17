# ------------------------------------------------------------------------------
# OtterWorks Monitoring Module
# CloudWatch log groups for each service
# ------------------------------------------------------------------------------

locals {
  common_tags = {
    Module  = "monitoring"
    Project = var.project
  }

  services = [
    "api-gateway",
    "auth-service",
    "file-service",
    "document-service",
    "collab-service",
    "notification-service",
    "search-service",
    "analytics-service",
    "admin-service",
    "audit-service",
    "web-app",
    "admin-dashboard",
  ]
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = toset(local.services)

  name              = "/otterworks/${var.environment}/${each.value}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Service = each.value
  })
}
