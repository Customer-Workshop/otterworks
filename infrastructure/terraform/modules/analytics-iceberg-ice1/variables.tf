variable "project" {
  description = "Project prefix"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "namespace" {
  description = "Migration namespace suffix"
  type        = string
  default     = "ice1"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "analytics_role_name" {
  description = "Existing analytics-service IRSA role to receive the namespaced lakehouse policy"
  type        = string
}
