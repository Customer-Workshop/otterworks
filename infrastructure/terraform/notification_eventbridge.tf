# ------------------------------------------------------------------------------
# Re-architected notification delivery: EventBridge -> SQS -> Lambda
#
# This is an ADDITIVE, namespaced migration target that sits alongside
# module.messaging (SNS -> SQS -> in-cluster consumer). It is disabled by
# default (var.notification_eventbridge_ns == "" => count = 0), so a plain
# `terraform apply` of `main` provisions nothing here and the golden-app path
# is untouched. Enable a namespaced instance for a migration run with:
#
#   terraform apply -var 'notification_eventbridge_ns=ebns1'
#
# Revert (one command):
#
#   terraform destroy -target='module.notification_eventbridge[0]'
# ------------------------------------------------------------------------------

variable "notification_eventbridge_ns" {
  description = <<-EOT
    Namespace suffix for the serverless notification pipeline. Empty (default)
    disables the module entirely so `main` stays the durable, reversible
    before-state. Set to a short token (e.g. "ebns1") to provision a namespaced
    EventBridge -> SQS -> Lambda pipeline for a migration run.
  EOT
  type        = string
  default     = ""
}

module "notification_eventbridge" {
  count  = var.notification_eventbridge_ns == "" ? 0 : 1
  source = "./modules/notification-eventbridge"

  project     = "otterworks"
  environment = var.environment
  ns          = var.notification_eventbridge_ns
  aws_region  = var.aws_region

  # Write to / read from the SAME tables the in-cluster consumer uses, so the
  # migrated path is measured against equivalent data and stays parity-exact.
  notifications_table_name = module.database.notifications_table_name
  notifications_table_arn  = module.database.notifications_table_arn
  preferences_table_name   = "otterworks-notification-preferences"

  log_retention_days = var.log_retention_days
}

# Least-privilege grant: let the migrated notification publisher (file-service)
# PutEvents to THIS namespaced bus only. Additive and count-gated — the base
# IRSA roles in main.tf are unchanged when disabled.
resource "aws_iam_role_policy" "publisher_put_events" {
  for_each = var.notification_eventbridge_ns == "" ? toset([]) : toset(["file-service"])

  name = "notification-eventbridge-${var.notification_eventbridge_ns}-putevents"
  role = module.irsa.role_names[each.key]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["events:PutEvents"]
      Resource = [module.notification_eventbridge[0].event_bus_arn]
    }]
  })
}

output "notification_eventbridge_bus_name" {
  description = "EventBridge bus name for the serverless notification pipeline (empty when disabled)."
  value       = var.notification_eventbridge_ns == "" ? "" : module.notification_eventbridge[0].event_bus_name
}

output "notification_eventbridge_queue_url" {
  description = "SQS queue URL for the serverless notification pipeline (empty when disabled)."
  value       = var.notification_eventbridge_ns == "" ? "" : module.notification_eventbridge[0].queue_url
}

output "notification_eventbridge_lambda" {
  description = "Lambda consumer function name for the serverless notification pipeline (empty when disabled)."
  value       = var.notification_eventbridge_ns == "" ? "" : module.notification_eventbridge[0].lambda_function_name
}
