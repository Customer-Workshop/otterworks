# OtterWorks Infrastructure - Application-Specific AWS Resources
# Shared platform (EKS, VPC, ingress) lives in platform-engineering-shared-services

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    bucket = "otterworks-terraform-state"
    key    = "otterworks/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "otterworks"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Data sources for shared platform
data "aws_eks_cluster" "platform" {
  name = var.eks_cluster_name
}

data "aws_eks_cluster_auth" "platform" {
  name = var.eks_cluster_name
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.platform.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.platform.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.platform.token
}

provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.platform.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.platform.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.platform.token
  }
}

# Modules
module "storage" {
  source      = "./modules/storage"
  environment = var.environment
  project     = "otterworks"
}

module "database" {
  source      = "./modules/database"
  environment = var.environment
  project     = "otterworks"
}

module "messaging" {
  source      = "./modules/messaging"
  environment = var.environment
  project     = "otterworks"
}

module "search" {
  source      = "./modules/search"
  environment = var.environment
  project     = "otterworks"
}

module "auth" {
  source      = "./modules/auth"
  environment = var.environment
  project     = "otterworks"
}
