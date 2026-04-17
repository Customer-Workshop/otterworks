# SQS queues and SNS topics for OtterWorks event-driven architecture

resource "aws_sns_topic" "events" {
  name = "${var.project}-events-${var.environment}"
}

resource "aws_sqs_queue" "notifications" {
  name                       = "${var.project}-notifications-${var.environment}"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20 # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Service = "notification-service" }
}

resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "${var.project}-notifications-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = { Service = "notification-service" }
}

resource "aws_sqs_queue" "analytics_events" {
  name                       = "${var.project}-analytics-events-${var.environment}"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 259200
  receive_wait_time_seconds  = 20

  tags = { Service = "analytics-service" }
}

resource "aws_sqs_queue" "search_indexing" {
  name                       = "${var.project}-search-indexing-${var.environment}"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20

  tags = { Service = "search-service" }
}

# SNS -> SQS subscriptions
resource "aws_sns_topic_subscription" "notifications" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notifications.arn

  filter_policy = jsonencode({
    eventType = ["file_shared", "comment_added", "document_edited", "user_mentioned"]
  })
}

resource "aws_sns_topic_subscription" "analytics" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.analytics_events.arn
}

resource "aws_sns_topic_subscription" "search_indexing" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.search_indexing.arn

  filter_policy = jsonencode({
    eventType = ["document_created", "document_updated", "document_deleted", "file_uploaded", "file_deleted"]
  })
}

# SQS policies to allow SNS to send messages
resource "aws_sqs_queue_policy" "notifications" {
  queue_url = aws_sqs_queue.notifications.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.notifications.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.events.arn } }
    }]
  })
}

output "notification_queue_url" {
  value = aws_sqs_queue.notifications.url
}

output "events_topic_arn" {
  value = aws_sns_topic.events.arn
}

variable "environment" { type = string }
variable "project" { type = string }
