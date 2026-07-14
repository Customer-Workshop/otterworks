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

# --- REPLATFORM: Aurora Serverless v2 (namespace aur1) ---
# Defaults OFF so `main`/default plans provision nothing new — the RDS
# before-state stays durable. Set true (e.g. -var enable_aurora_aur1=true) on
# the migration branch to provision the namespaced Aurora cluster alongside RDS.
variable "enable_aurora_aur1" {
  description = "Provision the namespaced Aurora Serverless v2 cluster (module.aurora_aur1) alongside the RDS before-state"
  type        = bool
  default     = false
}

variable "aurora_aur1_min_capacity" {
  description = "Aurora Serverless v2 minimum ACU for the aur1 cluster (0 = scale-to-zero)"
  type        = number
  default     = 0
}

variable "aurora_aur1_max_capacity" {
  description = "Aurora Serverless v2 maximum ACU for the aur1 cluster"
  type        = number
  default     = 4
}
