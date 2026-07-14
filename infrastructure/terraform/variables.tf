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

variable "enable_report_lambda" {
  description = "Opt-in flag for the namespaced report-service Lambda + API Gateway migration module (namespace lam1). Default false so the golden `main` deploy path (RDS/DynamoDB/S3/EKS) provisions cleanly without needing the Lambda zip pre-built. Set true (with the zip built via `mvn -Plambda package`) to provision the serverless report-service target alongside the always-on EKS pod."
  type        = bool
  default     = false
}
