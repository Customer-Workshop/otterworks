# ------------------------------------------------------------------------------
# OtterWorks Infrastructure - Application-Specific AWS Resources
# Shared platform (EKS, VPC, ingress) lives in platform-engineering-shared-services
# ------------------------------------------------------------------------------

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

# --- Data Sources for Shared Platform ---

data "aws_eks_cluster" "platform" {
  name = var.eks_cluster_name
}

data "aws_eks_cluster_auth" "platform" {
  name = var.eks_cluster_name
}

data "aws_vpc" "platform" {
  id = data.aws_eks_cluster.platform.vpc_config[0].vpc_id
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.platform.id]
  }

  tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
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

# --- Modules ---

module "storage" {
  source      = "./modules/storage"
  environment = var.environment
  project     = "otterworks"
}

module "database" {
  source      = "./modules/database"
  environment = var.environment
  project     = "otterworks"
  db_password = var.db_password
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

module "cache" {
  source              = "./modules/cache"
  environment         = var.environment
  project             = "otterworks"
  vpc_id              = data.aws_vpc.platform.id
  subnet_ids          = data.aws_subnets.private.ids
  allowed_cidr_blocks = [data.aws_vpc.platform.cidr_block]
}

module "monitoring" {
  source             = "./modules/monitoring"
  environment        = var.environment
  project            = "otterworks"
  log_retention_days = var.log_retention_days
}

module "irsa" {
  source            = "./modules/irsa"
  environment       = var.environment
  project           = "otterworks"
  namespace         = var.namespace
  oidc_provider_arn = var.oidc_provider_arn
  oidc_provider_url = data.aws_eks_cluster.platform.identity[0].oidc[0].issuer

  service_accounts = {
    "file-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket",
          ]
          Resource = [
            module.storage.file_bucket_arn,
            "${module.storage.file_bucket_arn}/*",
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
          ]
          Resource = [
            module.database.file_metadata_table_arn,
            "${module.database.file_metadata_table_arn}/index/*",
          ]
        },
      ]
    })

    "document-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "s3:GetObject",
            "s3:PutObject",
          ]
          Resource = [
            module.storage.file_bucket_arn,
            "${module.storage.file_bucket_arn}/*",
          ]
        },
        {
          Effect   = "Allow"
          Action   = ["sns:Publish"]
          Resource = [module.messaging.events_topic_arn]
        },
      ]
    })

    "notification-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:GetQueueAttributes",
          ]
          Resource = [module.messaging.notification_queue_arn]
        },
        {
          Effect = "Allow"
          Action = [
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:Query",
          ]
          Resource = [
            module.database.notifications_table_arn,
            "${module.database.notifications_table_arn}/index/*",
          ]
        },
        {
          Effect   = "Allow"
          Action   = ["ses:SendEmail", "ses:SendRawEmail"]
          Resource = ["*"]
        },
      ]
    })

    "search-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:GetQueueAttributes",
          ]
          Resource = [module.messaging.search_indexing_queue_arn]
        },
        {
          Effect = "Allow"
          Action = ["es:ESHttp*"]
          Resource = [
            module.search.opensearch_arn,
            "${module.search.opensearch_arn}/*",
          ]
        },
      ]
    })

    "analytics-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:GetQueueAttributes",
          ]
          Resource = [module.messaging.analytics_queue_arn]
        },
        {
          Effect = "Allow"
          Action = [
            "s3:PutObject",
            "s3:GetObject",
            "s3:ListBucket",
          ]
          Resource = [
            module.storage.data_lake_bucket_arn,
            "${module.storage.data_lake_bucket_arn}/*",
          ]
        },
      ]
    })

    "audit-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "dynamodb:PutItem",
            "dynamodb:GetItem",
            "dynamodb:Query",
            "dynamodb:BatchWriteItem",
          ]
          Resource = [
            module.database.audit_events_table_arn,
            "${module.database.audit_events_table_arn}/index/*",
          ]
        },
        {
          Effect = "Allow"
          Action = [
            "s3:PutObject",
          ]
          Resource = [
            module.storage.audit_archive_bucket_arn,
            "${module.storage.audit_archive_bucket_arn}/*",
          ]
        },
      ]
    })

    "auth-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "cognito-idp:AdminCreateUser",
            "cognito-idp:AdminGetUser",
            "cognito-idp:AdminUpdateUserAttributes",
            "cognito-idp:AdminDisableUser",
            "cognito-idp:AdminEnableUser",
            "cognito-idp:ListUsers",
          ]
          Resource = [module.auth.user_pool_arn]
        },
      ]
    })

    "admin-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "cognito-idp:ListUsers",
            "cognito-idp:AdminGetUser",
            "cognito-idp:AdminDisableUser",
            "cognito-idp:AdminEnableUser",
          ]
          Resource = [module.auth.user_pool_arn]
        },
        {
          Effect   = "Allow"
          Action   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics"]
          Resource = ["*"]
        },
      ]
    })

    "api-gateway" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["sns:Publish"]
          Resource = [module.messaging.events_topic_arn]
        },
      ]
    })

    "collab-service" = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["sns:Publish"]
          Resource = [module.messaging.events_topic_arn]
        },
      ]
    })
  }
}
