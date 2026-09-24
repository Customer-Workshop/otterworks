variable "namespace" {
  description = "Demo token <run>-<before|after> (CONTRACTS.md §3.1)."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,11}-(before|after)$", var.namespace))
    error_message = "namespace must match ^[a-z][a-z0-9]{1,11}-(before|after)$."
  }
}

variable "expires" {
  description = "Absolute UTC expiry, YYYY-MM-DDTHH:MM:SSZ (tag consumed by the reaper)."
  type        = string
  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$", var.expires))
    error_message = "expires must be an absolute UTC timestamp like 2026-09-27T15:00:00Z."
  }
}

variable "owner" {
  description = "Owner tag; MUST be otterworks-demo."
  type        = string
  default     = "otterworks-demo"
  validation {
    condition     = var.owner == "otterworks-demo"
    error_message = "owner must be otterworks-demo."
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "eks_cluster" {
  description = "EKS cluster whose node group AZ hosts the Db2 volume."
  type        = string
  default     = "otterworks-dev"
}

variable "db2_volume_az" {
  description = "Override the Db2 EBS volume AZ; defaults to the first AZ of the cluster's first node group."
  type        = string
  default     = ""
}

variable "db2_volume_size_gib" {
  type    = number
  default = 20
}
