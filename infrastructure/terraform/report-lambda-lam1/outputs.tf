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

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.report.endpoint
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "lambda_artifact_bucket" {
  description = "Private S3 bucket containing the Lambda deployment artifact"
  value       = aws_s3_bucket.lambda_artifact.bucket
}
