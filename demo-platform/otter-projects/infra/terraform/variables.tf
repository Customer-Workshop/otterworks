variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "cluster_name" {
  type    = string
  default = "otterworks-dev"
}

variable "platform_namespace" {
  type    = string
  default = "otterworks-platform"
}

variable "service_account" {
  type    = string
  default = "otter-projects"
}

variable "table_name" {
  type    = string
  default = "otterworks-projects"
}
