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
  description = <<-EOT
    Migration namespace suffix (e.g. "os1"). Applied to the collection name and
    every policy so concurrent/repeated migrations never collide. Revert is a
    terraform destroy of just this namespaced module.
  EOT
  type        = string
  default     = "os1"

  validation {
    condition     = can(regex("^[a-z0-9]{1,12}$", var.namespace))
    error_message = "Namespace must be lowercase alphanumeric, 1-12 characters."
  }
}

variable "vpc_id" {
  description = "VPC in which to place the OpenSearch Serverless VPC endpoint"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR allowed to reach the collection over the VPC endpoint (443)"
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for the OpenSearch Serverless VPC endpoint (private)"
  type        = list(string)
}

variable "data_access_principal_arns" {
  description = <<-EOT
    IAM principal ARNs granted data-access (read/write) on the collection.
    Typically the search-service IRSA role ARN. Passed in (rather than read from
    the IRSA module) so the IRSA policy can reference this collection's ARN
    without creating a dependency cycle.
  EOT
  type        = list(string)
}
