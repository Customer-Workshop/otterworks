output "api_endpoint" {
  description = "HTTP API invoke URL"
  value       = module.report_lambda_ea3c.api_endpoint
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.report_lambda_ea3c.lambda_function_name
}

output "lambda_alias_name" {
  description = "Traffic alias receiving API Gateway requests"
  value       = module.report_lambda_ea3c.lambda_alias_name
}

output "database_endpoint" {
  description = "Isolated RDS PostgreSQL endpoint"
  value       = module.report_lambda_ea3c.database_endpoint
}

output "log_group_name" {
  description = "Lambda CloudWatch log group"
  value       = module.report_lambda_ea3c.log_group_name
}

output "dashboard_name" {
  description = "CloudWatch dashboard containing Lambda verification metrics"
  value       = module.report_lambda_ea3c.dashboard_name
}

output "cold_start_metric_namespace" {
  description = "CloudWatch namespace containing the ColdStarts metric"
  value       = module.report_lambda_ea3c.cold_start_metric_namespace
}
