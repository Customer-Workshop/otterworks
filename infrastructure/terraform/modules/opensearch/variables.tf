variable "project" {
  description = "Project name used as prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "namespace" {
  description = "Namespace suffix for OpenSearch resources"
  type        = string
  default     = "os1"
}

variable "principal_arns" {
  description = "IAM principals allowed to access the collection"
  type        = list(string)
}
