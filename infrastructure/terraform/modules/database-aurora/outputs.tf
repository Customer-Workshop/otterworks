output "cluster_endpoint" {
  description = "Aurora writer (cluster) endpoint — set services' DB_HOST / DATABASE_URL to this to cut over"
  value       = aws_rds_cluster.aurora.endpoint
}

output "reader_endpoint" {
  description = "Aurora reader endpoint (load-balanced across replicas)"
  value       = aws_rds_cluster.aurora.reader_endpoint
}

output "port" {
  description = "Aurora PostgreSQL port"
  value       = aws_rds_cluster.aurora.port
}

output "database_name" {
  description = "Default database name on the Aurora cluster"
  value       = aws_rds_cluster.aurora.database_name
}

output "cluster_arn" {
  description = "ARN of the Aurora cluster"
  value       = aws_rds_cluster.aurora.arn
}

output "cluster_resource_id" {
  description = "Aurora cluster resource ID (used in rds-db:connect ARNs for IAM auth)"
  value       = aws_rds_cluster.aurora.cluster_resource_id
}

output "security_group_id" {
  description = "Security group ID protecting the Aurora cluster"
  value       = aws_security_group.aurora.id
}

output "iam_connect_policy_json" {
  description = "IAM policy JSON granting rds-db:connect for the configured IAM database users"
  value       = data.aws_iam_policy_document.rds_connect.json
}
