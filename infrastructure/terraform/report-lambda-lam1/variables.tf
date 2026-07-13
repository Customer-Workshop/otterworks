variable "aws_region" {
  description = "AWS region for the isolated report Lambda resources"
  type        = string
  default     = "us-east-2"
}

variable "namespace" {
  description = "Suffix used to isolate all report Lambda resources"
  type        = string
  default     = "lam1"
}

variable "db_name" {
  description = "RDS PostgreSQL database name"
  type        = string
  default     = "otterworks_reports"
}

variable "db_user" {
  description = "RDS PostgreSQL username"
  type        = string
  default     = "otterworks"
}

variable "db_password" {
  description = "RDS PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "lambda_memory" {
  description = "Lambda memory allocation in MB"
  type        = number
  default     = 2048
}

variable "lambda_jar_path" {
  description = "Path to the flat Lambda deployment JAR"
  type        = string
}

variable "lambda_reserved_concurrency" {
  description = "Maximum concurrent Lambda environments, bounded for the RDS connection budget"
  type        = number
  default     = 8
}

variable "lambda_provisioned_concurrency" {
  description = "Warm Lambda environments kept ready behind the live alias"
  type        = number
  default     = 3
}
