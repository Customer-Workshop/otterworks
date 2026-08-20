variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "project" {
  description = "Project name used as prefix for resource naming"
  type        = string
  default     = "otterworks"
}

variable "vpc_id" {
  description = "VPC the databases live in"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR allowed to reach the databases on 5432"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the database subnet group"
  type        = list(string)
}

variable "db_passwords" {
  description = "Master password per context (announcements, user-preferences, feedback)"
  type        = map(string)
  sensitive   = true

  validation {
    condition     = alltrue([for c in ["announcements", "user-preferences", "feedback"] : can(var.db_passwords[c])])
    error_message = "db_passwords must contain a password for each of: announcements, user-preferences, feedback."
  }
}

variable "engine_version" {
  description = "PostgreSQL engine version (16.x; the services are parity-proven against postgres:16)"
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  description = "Instance class for each extracted service database"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB per database"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling in GB per database"
  type        = number
  default     = 50
}
