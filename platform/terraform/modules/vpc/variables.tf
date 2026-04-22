variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to use"
  type        = number
  default     = 2
}

variable "cluster_name" {
  description = "EKS cluster name (used for subnet tagging)"
  type        = string
}

variable "enable_nat_gateway" {
  description = "Whether to create a NAT gateway for private subnet egress"
  type        = bool
  default     = false
}
