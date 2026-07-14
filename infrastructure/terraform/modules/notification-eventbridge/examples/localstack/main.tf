# LocalStack end-to-end harness for the notification-eventbridge module.
#
# Provisions the full pipeline (EventBridge bus + rule + SQS target + DLQ +
# Lambda + event source mapping + least-priv IAM + log group) against LocalStack
# via `tflocal`, so the re-architected path can be exercised end to end:
#
#   tflocal init && tflocal apply -auto-approve
#   awslocal events put-events --entries ...   # -> SQS -> Lambda -> DynamoDB
#
# This is test scaffolding only; it is never applied to real AWS.

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = ">= 5.0" }
    archive = { source = "hashicorp/archive", version = ">= 2.4" }
  }
}

module "notification_eventbridge" {
  source = "../.."

  project     = "otterworks"
  environment = "dev"
  ns          = "ebns1"

  notifications_table_name = "otterworks-notifications"
  preferences_table_name   = "otterworks-notification-preferences"

  # From within LocalStack-launched Lambda containers, the LocalStack API is
  # reachable at this DNS name.
  aws_endpoint_url = "http://localhost.localstack.cloud:4566"

  lambda_runtime = "python3.12"
}

output "event_bus_name" {
  value = module.notification_eventbridge.event_bus_name
}

output "queue_url" {
  value = module.notification_eventbridge.queue_url
}

output "lambda_function_name" {
  value = module.notification_eventbridge.lambda_function_name
}
