# ------------------------------------------------------------------------------
# OtterWorks Aurora Serverless v2 Module (namespace: aur1)
# Variables
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
  description = "Namespace suffix applied to every resource so parallel migration runs never collide"
  type        = string
  default     = "aur1"

  validation {
    condition     = can(regex("^[a-z0-9]{2,12}$", var.namespace))
    error_message = "Namespace must be lowercase alphanumeric, 2-12 characters."
  }
}

variable "db_password" {
  description = "Master password for the Aurora PostgreSQL cluster"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 8
    error_message = "Database password must be at least 8 characters."
  }
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version. Matched to the RDS before-state (15.x) so Flyway migrations apply identically."
  type        = string
  default     = "15.7"
}

variable "min_capacity" {
  description = "Aurora Serverless v2 minimum ACU. 0 enables scale-to-zero (auto-pause when idle)."
  type        = number
  default     = 0
}

variable "max_capacity" {
  description = "Aurora Serverless v2 maximum ACU."
  type        = number
  default     = 4
}

variable "seconds_until_auto_pause" {
  description = "Idle seconds before Serverless v2 scales to zero (only used when min_capacity = 0)."
  type        = number
  default     = 300
}

variable "vpc_id" {
  description = "VPC ID for the Aurora security group"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the Aurora subnet group"
  type        = list(string)
}

variable "vpc_cidr" {
  description = "VPC CIDR block for security group ingress rules"
  type        = string
}
