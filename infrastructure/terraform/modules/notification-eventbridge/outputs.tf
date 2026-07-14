output "event_bus_name" {
  description = "Name of the custom EventBridge bus domain events are published to."
  value       = aws_cloudwatch_event_bus.notifications.name
}

output "event_bus_arn" {
  description = "ARN of the custom EventBridge bus."
  value       = aws_cloudwatch_event_bus.notifications.arn
}

output "event_rule_name" {
  description = "Name of the EventBridge rule routing domain events to SQS."
  value       = aws_cloudwatch_event_rule.notifications.name
}

output "event_rule_arn" {
  description = "ARN of the EventBridge rule."
  value       = aws_cloudwatch_event_rule.notifications.arn
}

output "queue_url" {
  description = "URL of the SQS queue the Lambda consumer polls."
  value       = aws_sqs_queue.notifications.url
}

output "queue_arn" {
  description = "ARN of the SQS queue."
  value       = aws_sqs_queue.notifications.arn
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.notifications_dlq.url
}

output "lambda_function_name" {
  description = "Name of the notification consumer Lambda function."
  value       = aws_lambda_function.consumer.function_name
}

output "lambda_function_arn" {
  description = "ARN of the notification consumer Lambda function."
  value       = aws_lambda_function.consumer.arn
}

output "lambda_role_arn" {
  description = "ARN of the least-privilege IAM role assumed by the Lambda consumer."
  value       = aws_iam_role.lambda.arn
}

output "lambda_log_group" {
  description = "CloudWatch log group for the Lambda consumer."
  value       = aws_cloudwatch_log_group.lambda.name
}
