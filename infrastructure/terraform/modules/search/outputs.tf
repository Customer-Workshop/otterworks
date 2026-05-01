output "meilisearch_security_group_id" {
  description = "Security group ID for MeiliSearch"
  value       = aws_security_group.meilisearch.id
}

output "meilisearch_ecs_cluster_arn" {
  description = "ARN of the MeiliSearch ECS cluster"
  value       = aws_ecs_cluster.meilisearch.arn
}

output "meilisearch_ecs_service_arn" {
  description = "ARN of the MeiliSearch ECS service"
  value       = aws_ecs_service.meilisearch.id
}

output "meilisearch_service_name" {
  description = "Name of the MeiliSearch ECS service"
  value       = aws_ecs_service.meilisearch.name
}
