# ------------------------------------------------------------------------------
# Variables — messaging-serverless-<ns> module
# Re-architect target for notification-service: EventBridge + SQS + Lambda.
# This module lives ALONGSIDE modules/messaging (the self-managed before-state);
# it never replaces or mutates it.
# ------------------------------------------------------------------------------

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "project" {
  description = "Project name used as prefix for resource naming"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project))
    error_message = "Project name must be lowercase alphanumeric with hyphens, 2-21 characters."
  }
}

variable "namespace" {
  description = "Namespace suffix applied to every resource so concurrent/repeat migration runs never collide (e.g. evt1)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,15}$", var.namespace))
    error_message = "Namespace must be lowercase alphanumeric with hyphens, 1-16 characters."
  }
}

variable "notifications_table_arn" {
  description = "ARN of the DynamoDB notifications table the Lambda consumer writes to (reused from module.database — read/write only, no schema change)."
  type        = string
}

variable "notifications_table_name" {
  description = "Name of the DynamoDB notifications table, passed to the Lambda as env."
  type        = string
}

variable "preferences_table_name" {
  description = "Name of the DynamoDB notification-preferences table, passed to the Lambda as env."
  type        = string
  default     = "otterworks-notification-preferences"
}

variable "notification_event_types" {
  description = "Domain event types routed to the notification pipeline. Mirrors the SNS filter policy in modules/messaging so the re-architected path receives the SAME events."
  type        = list(string)
  default     = ["file_shared", "comment_added", "document_edited", "user_mentioned"]
}

variable "lambda_jar_path" {
  description = "Path to the built notification Lambda deployment jar (produced by ./gradlew :lambdaJar in services/notification-service). Relative to this repo's infrastructure/terraform dir."
  type        = string
  default     = "../../services/notification-service/build/libs/notification-service-lambda.jar"
}

variable "lambda_handler" {
  description = "Fully-qualified Lambda handler class::method (AWS Java runtime)."
  type        = string
  default     = "com.otterworks.notification.lambda.NotificationLambdaHandler::handleRequest"
}

variable "lambda_runtime" {
  description = "Lambda managed runtime."
  type        = string
  default     = "java17"
}

variable "lambda_memory_mb" {
  description = "Lambda memory size (MB)."
  type        = number
  default     = 512
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout (seconds). Must be <= SQS visibility timeout."
  type        = number
  default     = 30
}

variable "ses_from_email" {
  description = "Verified SES from-address for email notifications."
  type        = string
  default     = "notifications@otterworks.io"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the Lambda log group."
  type        = number
  default     = 14
}
