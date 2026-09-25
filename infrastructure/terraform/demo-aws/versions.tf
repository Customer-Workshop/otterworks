terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # One state per token (CONTRACTS.md §3.2):
  #   bucket = otterworks-terraform-state
  #   key    = otterworks/demo/<token>/terraform.tfstate
  # Supplied by scripts/deploy-demo.sh via -backend-config.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}
