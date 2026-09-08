# ------------------------------------------------------------------------------
# Otter Projects — app-specific infrastructure
#
#   - DynamoDB single table `otterworks-projects` (PROJECT#/TICKET#/COMMENT#/
#     EVENT#/WEBHOOK# items)
#   - IRSA role for the otter-projects ServiceAccount, scoped to that table only
#
# Separate Terraform root with its own state key. The account id is resolved
# from the caller identity and never hard-coded.
# ------------------------------------------------------------------------------
terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # `key` is supplied per cluster by scripts/deploy-otter-projects.sh via
  # `-backend-config` so a second cluster never rewrites this one's IRSA trust.
  backend "s3" {
    bucket = "otterworks-terraform-state"
    key    = "demo-platform/otter-projects/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "otterworks"
      Component = "otter-projects"
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
  app_sa     = "system:serviceaccount:${var.platform_namespace}:${var.service_account}"
}
