output "api_endpoint" {
  description = "HTTP API invoke URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.report.function_name
}

output "lambda_alias_name" {
  description = "Traffic alias receiving API Gateway requests"
  value       = aws_lambda_alias.report.name
}

output "database_endpoint" {
  description = "Isolated RDS PostgreSQL endpoint"
  value       = aws_db_instance.report.endpoint
}

output "log_group_name" {
  description = "Lambda CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "dashboard_name" {
  description = "CloudWatch dashboard containing Lambda verification metrics"
  value       = aws_cloudwatch_dashboard.report.dashboard_name
}

output "cold_start_metric_namespace" {
  description = "CloudWatch namespace containing the ColdStarts metric"
  value       = "OtterWorks/ReportLambda/${var.namespace}"
}
