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

variable "db_password" {
  description = "Master password for the Aurora PostgreSQL cluster. Still required even with IAM auth enabled (bootstrap/admin user)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 8
    error_message = "Database password must be at least 8 characters."
  }
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version. Must match the RDS PostgreSQL major version (15) for a drop-in cutover."
  type        = string
  default     = "15.7"
}

variable "min_capacity" {
  description = "Aurora Serverless v2 minimum capacity in ACUs"
  type        = number
  default     = 0.5
}

variable "max_capacity" {
  description = "Aurora Serverless v2 maximum capacity in ACUs"
  type        = number
  default     = 4
}

variable "instance_count" {
  description = "Number of Serverless v2 instances in the cluster (1 writer; >1 adds read replicas)"
  type        = number
  default     = 1
}

variable "iam_db_users" {
  description = "Database roles that may authenticate via IAM (used to build rds-db:connect resource ARNs). These roles must be GRANTed rds_iam in-database."
  type        = list(string)
  default     = ["otterworks"]
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
