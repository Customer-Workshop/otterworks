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

resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.project}-${var.environment}"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = var.opensearch_instance_type
    instance_count = var.opensearch_instance_count
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

  tags = merge(local.common_tags, {
    Service = "search-service"
  })
}
