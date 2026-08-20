output "db_endpoints" {
  description = "Map of context name to its database endpoint (host:port)"
  value       = { for k, v in aws_db_instance.portal : k => v.endpoint }
}

output "db_names" {
  description = "Map of context name to database name"
  value       = { for k, v in aws_db_instance.portal : k => v.db_name }
}

output "db_usernames" {
  description = "Map of context name to database master username"
  value       = { for k, v in aws_db_instance.portal : k => v.username }
}

# What the deploy step sets as SPRING_DATASOURCE_URL for each extracted service's Helm
# release. The password is never an output; it is supplied to Helm at deploy time.
output "jdbc_urls" {
  description = "Map of context name to the JDBC URL its service is configured with"
  value       = { for k, v in aws_db_instance.portal : k => "jdbc:postgresql://${v.endpoint}/${v.db_name}" }
}

output "db_security_group_id" {
  description = "Security group guarding the extracted portal databases"
  value       = aws_security_group.portal_db.id
}
