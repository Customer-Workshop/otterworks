terraform {
  required_version = ">= 1.6"

  required_providers {
    airbyte = {
      source  = "airbytehq/airbyte"
      version = "~> 0.13"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Key is supplied per namespace at init time:
  #   terraform init -backend-config="key=ow-tp/airbyte/<ns>.tfstate"
  backend "s3" {
    bucket = "otterworks-terraform-state"
    region = "us-east-1"
  }
}

# Credentials come from the environment, never from tfvars:
#   AIRBYTE_CLIENT_ID / AIRBYTE_CLIENT_SECRET      (Airbyte Cloud application)
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY      (landing bucket + reader user)
#   TF_VAR_databricks_host / TF_VAR_databricks_client_id / TF_VAR_databricks_client_secret
provider "airbyte" {
  client_id     = var.airbyte_client_id
  client_secret = var.airbyte_client_secret
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "otterworks-tp"
      ManagedBy = "terraform"
      Track     = "airbyte"
      Namespace = var.namespace
    }
  }
}

locals {
  prefix = "ow-tp-airbyte-${var.namespace}"
  # The destination wants a bare hostname; accept either form of the secret.
  databricks_hostname = trimsuffix(replace(var.databricks_host, "/^https?:\\/\\//", ""), "/")
}
