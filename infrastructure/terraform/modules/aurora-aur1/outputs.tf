# ------------------------------------------------------------------------------
# OtterWorks Aurora Serverless v2 Module (namespace: aur1)
# Outputs
# ------------------------------------------------------------------------------

output "aurora_endpoint" {
  description = "Aurora Serverless v2 writer endpoint (host:port style, matches rds_endpoint shape)"
  value       = "${aws_rds_cluster.aurora.endpoint}:${aws_rds_cluster.aurora.port}"
}

output "aurora_writer_host" {
  description = "Aurora writer endpoint host only"
  value       = aws_rds_cluster.aurora.endpoint
}

output "aurora_reader_endpoint" {
  description = "Aurora Serverless v2 reader endpoint"
  value       = aws_rds_cluster.aurora.reader_endpoint
}

output "aurora_port" {
  description = "Aurora cluster port"
  value       = aws_rds_cluster.aurora.port
}

output "aurora_database_name" {
  description = "Logical database name (identical to the RDS before-state)"
  value       = aws_rds_cluster.aurora.database_name
}

output "aurora_arn" {
  description = "ARN of the Aurora cluster"
  value       = aws_rds_cluster.aurora.arn
}

output "aurora_cluster_resource_id" {
  description = "Cluster resource id (stable id usable to scope a future rds-db:connect IAM policy)"
  value       = aws_rds_cluster.aurora.cluster_resource_id
}
