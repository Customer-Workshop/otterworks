variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "ecr_prefix" {
  description = "Prefix for ECR repository names"
  type        = string
  default     = "otterworks/"
}

variable "service_names" {
  description = "List of service names to create ECR repositories for"
  type        = list(string)
}
