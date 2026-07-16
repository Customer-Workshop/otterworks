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

variable "dashboard_service_account" {
  type    = string
  default = "demo-ops-dashboard"
}

variable "control_table_name" {
  type    = string
  default = "otterworks-demo-control"
}

# DNS/TLS is gated until the domain is registered. Flip to true and set
# dns_zone_name once otterworks.xyz exists in Route53.
variable "enable_dns" {
  type    = bool
  default = false
}

variable "dns_zone_name" {
  type    = string
  default = "otterworks.xyz"
}

# Shared data-plane resources the reaper must be able to GC per-tenant slices of.
# Prefix match keeps the policy stable as tables/buckets are added.
variable "shared_dynamodb_table_prefix" {
  type    = string
  default = "otterworks-"
}

variable "shared_s3_bucket_prefix" {
  type    = string
  default = "otterworks-"
}
