variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "namespace" {
  description = "Kubernetes namespace for OtterWorks services"
  type        = string
  default     = "otterworks"
}

variable "db_password" {
  description = "Master password for the RDS PostgreSQL instance"
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "meilisearch_master_key" {
  description = "MeiliSearch master key (required for production)"
  type        = string
  default     = ""
  sensitive   = true
}

# --- Analytics lakehouse (RE-ARCHITECT target: S3 + Iceberg + Glue + Athena) ---
# Additive and OFF by default so `main` (the golden app) provisions exactly the
# durable PostgreSQL "before". Set to true (with a namespace) to stand up the
# lakehouse alongside it; revert with `terraform destroy -target=module.analytics_lakehouse`.

variable "enable_analytics_lakehouse" {
  description = "Provision the namespaced analytics S3 + Iceberg lakehouse (Glue + Athena) alongside the existing store."
  type        = bool
  default     = false
}

variable "analytics_lakehouse_namespace" {
  description = "Namespace suffix for the analytics lakehouse module so concurrent runs never collide."
  type        = string
  default     = "ns1"
}
