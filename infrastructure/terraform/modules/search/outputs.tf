output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint URL"
  value       = aws_opensearch_domain.main.endpoint
}

output "opensearch_arn" {
  description = "ARN of the OpenSearch domain"
  value       = aws_opensearch_domain.main.arn
}

output "opensearch_domain_name" {
  description = "OpenSearch domain name"
  value       = aws_opensearch_domain.main.domain_name
}
