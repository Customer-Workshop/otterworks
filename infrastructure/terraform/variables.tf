variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "eks_cluster_name" {
  description = "Name of the shared EKS cluster"
  type        = string
  default     = "workshop-dev"
}

variable "namespace" {
  description = "Kubernetes namespace for OtterWorks"
  type        = string
  default     = "decomposition-dev"
}
