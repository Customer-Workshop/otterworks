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
  default     = 7
}

variable "meilisearch_master_key" {
  description = "MeiliSearch master key (required for production)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "creator_tag" {
  description = "Value of the `creator` tag applied to every resource in this layer"
  type        = string
  default     = "partner-workshops"
}

variable "enable_shared_cache" {
  description = "Provision the shared ElastiCache Redis. Tenants run Redis in-cluster, so leave off unless the legacy shared deploy is in use."
  type        = bool
  default     = false
}

variable "enable_shared_search" {
  description = "Provision the shared ECS Fargate MeiliSearch. Tenants run MeiliSearch in-cluster, so leave off unless the legacy shared deploy is in use."
  type        = bool
  default     = false
}

variable "s3_force_destroy" {
  description = "Allow `terraform destroy` to empty and delete the application S3 buckets (demo data only)"
  type        = bool
  default     = true
}
