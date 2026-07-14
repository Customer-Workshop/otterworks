output "lambda_function_name" {
  description = "Name of the report-service Lambda function."
  value       = aws_lambda_function.report.function_name
}

output "lambda_function_arn" {
  description = "ARN of the report-service Lambda function."
  value       = aws_lambda_function.report.arn
}

output "lambda_role_arn" {
  description = "ARN of the least-privilege Lambda execution role."
  value       = aws_iam_role.lambda_exec.arn
}

output "api_endpoint" {
  description = "Base HTTPS endpoint of the API Gateway fronting the report-service Lambda. Set the gateway's REPORT_SERVICE_URL to this to flip report traffic onto the serverless path."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_id" {
  description = "API Gateway (HTTP API) ID."
  value       = aws_apigatewayv2_api.report.id
}

output "log_group_name" {
  description = "CloudWatch log group for the Lambda."
  value       = aws_cloudwatch_log_group.lambda.name
}
