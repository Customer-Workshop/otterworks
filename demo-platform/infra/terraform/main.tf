# ------------------------------------------------------------------------------
# OtterWorks Demo Platform — control-plane infrastructure
#
# Durable, tenant-independent resources for the demo ops platform:
#   - DynamoDB control table (state store: registry, locks, reaper config, audit)
#   - IRSA role for the dashboard + runner (scoped, NOT the tenant wildcard)
#   - (optional) Route53 hosted zone + IAM for external-dns / cert-manager DNS-01
#
# Separate Terraform root from the app infra; own state key. Account ID is never
# hard-coded — it is resolved at plan time from the caller identity.
# ------------------------------------------------------------------------------
terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  backend "s3" {
    bucket = "otterworks-terraform-state"
    key    = "demo-platform/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "otterworks"
      Component = "demo-platform"
      ManagedBy = "terraform"
      Layer     = "control-plane"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  oidc_url   = replace(data.aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
  oidc_arn   = "arn:aws:iam::${local.account_id}:oidc-provider/${local.oidc_url}"

  # Service account the dashboard + runner Jobs run as.
  dashboard_sa = "system:serviceaccount:${var.platform_namespace}:${var.dashboard_service_account}"
}
