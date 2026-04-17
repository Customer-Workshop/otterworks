# OpenSearch domain for OtterWorks full-text search

resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.project}-${var.environment}"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = "t3.small.search"
    instance_count = 1 # Single node for dev, scale for prod
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
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

  tags = {
    Service = "search-service"
  }
}

output "opensearch_endpoint" {
  value = aws_opensearch_domain.main.endpoint
}

variable "environment" { type = string }
variable "project" { type = string }
