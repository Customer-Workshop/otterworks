output "user_pool_id" {
  description = "Cognito user pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN"
  value       = aws_cognito_user_pool.main.arn
}

output "user_pool_client_id" {
  description = "Cognito web client ID"
  value       = aws_cognito_user_pool_client.web.id
}

output "admin_client_id" {
  description = "Cognito admin dashboard client ID"
  value       = aws_cognito_user_pool_client.admin.id
}
