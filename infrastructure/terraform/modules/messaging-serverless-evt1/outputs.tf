output "event_bus_name" {
  description = "EventBridge bus that domain-event publishers target for the serverless notification path."
  value       = aws_cloudwatch_event_bus.events.name
}

output "event_bus_arn" {
  description = "EventBridge bus ARN."
  value       = aws_cloudwatch_event_bus.events.arn
}

output "event_rule_arn" {
  description = "EventBridge rule ARN (event-type filter -> SQS)."
  value       = aws_cloudwatch_event_rule.notifications.arn
}

output "notification_queue_url" {
  description = "SQS queue URL buffering events for the Lambda consumer."
  value       = aws_sqs_queue.notifications.url
}

output "notification_queue_arn" {
  description = "SQS queue ARN."
  value       = aws_sqs_queue.notifications.arn
}

output "notification_dlq_url" {
  description = "SQS dead-letter queue URL."
  value       = aws_sqs_queue.notifications_dlq.url
}

output "lambda_function_name" {
  description = "Name of the serverless notification consumer Lambda."
  value       = aws_lambda_function.consumer.function_name
}

output "lambda_function_arn" {
  description = "ARN of the serverless notification consumer Lambda."
  value       = aws_lambda_function.consumer.arn
}

output "lambda_role_arn" {
  description = "Least-privilege IAM role assumed by the Lambda."
  value       = aws_iam_role.lambda.arn
}

output "lambda_log_group" {
  description = "CloudWatch Logs group for the Lambda."
  value       = aws_cloudwatch_log_group.lambda.name
}
