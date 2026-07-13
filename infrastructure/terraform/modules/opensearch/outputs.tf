output "collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = aws_opensearchserverless_collection.this.collection_endpoint
}

output "dashboard_endpoint" {
  description = "OpenSearch Serverless dashboard endpoint"
  value       = aws_opensearchserverless_collection.this.dashboard_endpoint
}

output "collection_arn" {
  description = "OpenSearch Serverless collection ARN"
  value       = aws_opensearchserverless_collection.this.arn
}

output "collection_id" {
  description = "OpenSearch Serverless collection ID"
  value       = aws_opensearchserverless_collection.this.id
}

output "collection_name" {
  description = "OpenSearch Serverless collection name"
  value       = local.collection_name
}
