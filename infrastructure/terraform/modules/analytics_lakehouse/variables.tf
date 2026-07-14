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
  description = <<-EOT
    Namespace suffix applied to every resource in this module so concurrent
    migration runs / per-tenant demos never collide. Kept short and DNS/Glue
    safe (lowercase alphanumeric, 1-12 chars).
  EOT
  type        = string
  default     = "ns1"

  validation {
    condition     = can(regex("^[a-z0-9]{1,12}$", var.namespace))
    error_message = "Namespace must be lowercase alphanumeric, 1-12 characters."
  }
}

variable "data_lake_bucket_name" {
  description = "Name of the existing analytics data-lake S3 bucket (from the storage module) that backs the Iceberg warehouse."
  type        = string
}

variable "data_lake_bucket_arn" {
  description = "ARN of the existing analytics data-lake S3 bucket that backs the Iceberg warehouse."
  type        = string
}

variable "warehouse_prefix" {
  description = "Key prefix inside the data-lake bucket for the Iceberg warehouse."
  type        = string
  default     = "iceberg"
}

variable "events_table_name" {
  description = "Iceberg table name for the analytics event log."
  type        = string
  default     = "analytics_events"
}
