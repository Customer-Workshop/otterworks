terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "otterworks"
      Migration   = "report-lambda"
      Namespace   = var.namespace
      ManagedBy   = "terraform"
      Environment = "migration"
    }
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

module "report_lambda_ea3c" {
  source = "../modules/report-lambda"

  namespace             = var.namespace
  aws_region            = var.aws_region
  vpc_id                = data.aws_vpc.default.id
  vpc_cidr_block        = data.aws_vpc.default.cidr_block
  subnet_ids            = data.aws_subnets.default.ids
  lambda_jar_path       = var.lambda_jar_path
  lambda_memory         = var.lambda_memory
  analytics_service_url = var.analytics_service_url
  audit_service_url     = var.audit_service_url
  auth_service_url      = var.auth_service_url
}
