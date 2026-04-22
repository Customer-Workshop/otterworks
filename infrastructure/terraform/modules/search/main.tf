# ------------------------------------------------------------------------------
# OtterWorks Search Module
# OpenSearch domain for full-text search
# ------------------------------------------------------------------------------

locals {
  common_tags = {
    Module  = "search"
    Project = var.project
  }
}

# --- OpenSearch Security Group ---

resource "aws_security_group" "opensearch" {
  name        = "${var.project}-opensearch-${var.environment}"
  description = "Security group for OtterWorks OpenSearch"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}

resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.project}-${var.environment}"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = var.opensearch_instance_type
    instance_count = var.opensearch_instance_count
  }

  vpc_options {
    subnet_ids         = [var.subnet_ids[0]]
    security_group_ids = [aws_security_group.opensearch.id]
  }

  ebs_options {
    ebs_enabled = true
    volume_size = var.opensearch_volume_size
    volume_type = "gp3"
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:*"
      Resource  = "arn:aws:es:*:*:domain/${var.project}-${var.environment}/*"
    }]
  })

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}
