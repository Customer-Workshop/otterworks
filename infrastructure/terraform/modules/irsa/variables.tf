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
  description = "Kubernetes namespace for the service accounts"
  type        = string
  default     = "decomposition-dev"
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS OIDC identity provider"
  type        = string
}

variable "oidc_provider_url" {
  description = "URL of the EKS OIDC identity provider"
  type        = string
}

variable "service_accounts" {
  description = "Map of service account name to IAM policy JSON document"
  type        = map(string)
}
