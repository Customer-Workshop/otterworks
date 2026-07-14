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

variable "namespace_suffix" {
  description = "Isolation namespace suffix applied to every resource in this module so parallel migration runs never collide (e.g. lam1)."
  type        = string
  default     = "lam1"

  validation {
    condition     = can(regex("^[a-z0-9]{1,8}$", var.namespace_suffix))
    error_message = "namespace_suffix must be lowercase alphanumeric, 1-8 chars."
  }
}

variable "vpc_id" {
  description = "VPC ID hosting the Lambda ENIs and RDS."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for the Lambda VPC configuration (must reach RDS + dependent services)."
  type        = list(string)
}

variable "lambda_package_path" {
  description = "Path to the report-service Lambda deployment zip (lib/ layout; mvn -Plambda package -> target/report-service-lambda.zip)."
  type        = string
  default     = "../../services/report-service/target/report-service-lambda.zip"
}

variable "lambda_handler" {
  description = "Lambda handler FQCN (RequestStreamHandler)."
  type        = string
  default     = "com.otterworks.report.lambda.StreamLambdaHandler::handleRequest"
}

variable "lambda_runtime" {
  description = "Lambda Java runtime. The report-service jar targets bytecode 1.8, which runs on the managed Java 11/17 runtimes."
  type        = string
  default     = "java17"
}

variable "lambda_memory_mb" {
  description = "Lambda memory (MB). CPU scales with memory."
  type        = number
  default     = 1024
}

variable "lambda_timeout_s" {
  description = "Lambda timeout (seconds). Must exceed cold-start init + report request latency."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda log group."
  type        = number
  default     = 30
}

# --- Application configuration (mirrors the EKS report-service env; no contract change) ---

variable "db_host" {
  description = "PostgreSQL host the report-service connects to (RDS endpoint)."
  type        = string
}

variable "db_port" {
  description = "PostgreSQL port."
  type        = string
  default     = "5432"
}

variable "db_name" {
  description = "Report-service database name."
  type        = string
  default     = "otterworks_reports"
}

variable "db_user" {
  description = "Report-service database user."
  type        = string
  default     = "otterworks"
}

variable "db_password" {
  description = "Report-service database password."
  type        = string
  sensitive   = true
}

variable "analytics_service_url" {
  description = "Analytics service base URL used by the report generation worker."
  type        = string
  default     = ""
}

variable "audit_service_url" {
  description = "Audit service base URL used by the report generation worker."
  type        = string
  default     = ""
}

variable "auth_service_url" {
  description = "Auth service base URL used by the report generation worker."
  type        = string
  default     = ""
}
