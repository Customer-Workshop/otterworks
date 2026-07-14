# ------------------------------------------------------------------------------
# OtterWorks Notification EventBridge Module — variables
# ------------------------------------------------------------------------------

variable "project" {
  description = "Project name used as prefix for resource naming"
  type        = string
  default     = "otterworks"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project))
    error_message = "Project name must be lowercase alphanumeric with hyphens, 2-21 characters."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "ns" {
  description = <<-EOT
    Namespace suffix applied to the module's resources so concurrent
    migration runs (and parent/child fan-out) never collide. Keep short:
    it is embedded in resource names alongside project/environment.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,18}$", var.ns))
    error_message = "ns must be lowercase alphanumeric with hyphens, 1-19 characters."
  }
}

variable "notifications_table_name" {
  description = "DynamoDB notifications table the Lambda consumer writes to (shared with the in-cluster consumer for parity)."
  type        = string
  default     = "otterworks-notifications"
}

variable "notifications_table_arn" {
  description = "ARN of the DynamoDB notifications table (for least-privilege IAM). Defaults to a wildcard-scoped ARN built from the table name when not supplied."
  type        = string
  default     = ""
}

variable "preferences_table_name" {
  description = "DynamoDB notification-preferences table the Lambda consumer reads (falls back to defaults when an item is absent, identical to the in-cluster consumer)."
  type        = string
  default     = "otterworks-notification-preferences"
}

variable "preferences_table_arn" {
  description = "ARN of the DynamoDB notification-preferences table (for least-privilege IAM). Defaults to a wildcard-scoped ARN built from the table name when not supplied."
  type        = string
  default     = ""
}

variable "ses_from_email" {
  description = "From address used for email delivery attempts (parity with SES_FROM_EMAIL in the in-cluster consumer)."
  type        = string
  default     = "notifications@otterworks.io"
}

variable "event_source_names" {
  description = "EventBridge event `source` values the rule matches (one per domain-event publisher migrated onto EventBridge). Scoped to file-service, the notification producer whose events conform to the SqsNotificationMessage model the consumer expects."
  type        = list(string)
  default     = ["otterworks.file-service"]
}

variable "event_detail_types" {
  description = "Domain event types (EventBridge `detail-type`) routed to the notification pipeline. Mirrors the SNS notification filter policy."
  type        = list(string)
  default     = ["file_shared", "comment_added", "document_edited", "user_mentioned"]
}

variable "lambda_runtime" {
  description = "Lambda runtime for the notification consumer."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout_seconds" {
  description = "Lambda function timeout."
  type        = number
  default     = 30
}

variable "lambda_memory_mb" {
  description = "Lambda function memory size (MB)."
  type        = number
  default     = 256
}

variable "lambda_batch_size" {
  description = "Max SQS records delivered to the Lambda per invocation."
  type        = number
  default     = 10
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda log group."
  type        = number
  default     = 14
}

variable "aws_region" {
  description = "AWS region (used only to synthesize default table ARNs when explicit ARNs are not passed)."
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account id (used only to synthesize default table ARNs when explicit ARNs are not passed). Resolved automatically when left empty."
  type        = string
  default     = ""
}

variable "aws_endpoint_url" {
  description = <<-EOT
    Optional AWS endpoint override injected into the Lambda so it targets a
    local emulator (LocalStack) instead of real AWS. Leave empty in real AWS —
    the SDK then uses default endpoints. Mirrors AWS_ENDPOINT_URL used by the
    in-cluster services for local runs.
  EOT
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional tags merged onto every resource in the module."
  type        = map(string)
  default     = {}
}
