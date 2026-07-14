variable "namespace" {
  description = "Suffix applied to every migration resource"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{2,12}$", var.namespace))
    error_message = "Namespace must be 2-12 lowercase letters, digits, or hyphens."
  }
}

variable "aws_region" {
  description = "AWS region for the migration resources"
  type        = string
}

variable "vpc_id" {
  description = "VPC containing the Lambda, RDS Proxy, and RDS instance"
  type        = string
}

variable "vpc_cidr_block" {
  description = "VPC CIDR used for DNS resolver egress"
  type        = string
}

variable "subnet_ids" {
  description = "Subnets spanning at least two availability zones"
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "At least two subnets are required."
  }
}

variable "lambda_jar_path" {
  description = "Path to the flat Lambda deployment JAR"
  type        = string
}

variable "lambda_memory" {
  description = "Lambda memory allocation in MB"
  type        = number
  default     = 2048
}

variable "lambda_reserved_concurrency" {
  description = "Maximum concurrent Lambda environments"
  type        = number
  default     = 4
}

variable "lambda_provisioned_concurrency" {
  description = "Warm environments retained on the live alias; zero preserves scale-to-zero and exposes cold starts"
  type        = number
  default     = 0
}

variable "database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "otterworks_reports"
}

variable "database_user" {
  description = "PostgreSQL master username"
  type        = string
  default     = "otterworks"
}

variable "database_instance_class" {
  description = "RDS instance class for the isolated migration database"
  type        = string
  default     = "db.t4g.micro"
}

variable "analytics_service_url" {
  description = "Analytics service URL used while generating reports"
  type        = string
  default     = "http://analytics-service:8088"
}

variable "audit_service_url" {
  description = "Audit service URL used while generating reports"
  type        = string
  default     = "http://audit-service:8090"
}

variable "auth_service_url" {
  description = "Auth service URL used by report-service"
  type        = string
  default     = "http://auth-service:8081"
}
