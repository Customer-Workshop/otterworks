package com.otterworks.notification.config

data class AppConfig(
    val port: Int,
    val awsRegion: String,
    val awsEndpointUrl: String?,
    val sqsQueueUrl: String,
    val snsTopicArn: String,
    val dynamoDbTableNotifications: String,
    val dynamoDbTablePreferences: String,
    val sesFromEmail: String,
    val sqsPollIntervalMs: Long,
    val sqsMaxMessages: Int,
    val sqsWaitTimeSeconds: Int,
) {
    companion object {
        fun load(): AppConfig {
            return AppConfig(
                port = System.getenv("PORT")?.toIntOrNull() ?: 8086,
                awsRegion = System.getenv("AWS_REGION") ?: "us-east-1",
                awsEndpointUrl = System.getenv("AWS_ENDPOINT_URL"),
                sqsQueueUrl = System.getenv("SQS_QUEUE_URL")
                    ?: "http://localhost:4566/000000000000/otterworks-notifications",
                snsTopicArn = System.getenv("SNS_TOPIC_ARN")
                    ?: "arn:aws:sns:us-east-1:000000000000:otterworks-events",
                dynamoDbTableNotifications = System.getenv("DYNAMODB_TABLE_NOTIFICATIONS")
                    ?: "otterworks-notifications",
                dynamoDbTablePreferences = System.getenv("DYNAMODB_TABLE_PREFERENCES")
                    ?: "otterworks-notification-preferences",
                sesFromEmail = System.getenv("SES_FROM_EMAIL")
                    ?: "notifications@otterworks.io",
                sqsPollIntervalMs = System.getenv("SQS_POLL_INTERVAL_MS")?.toLongOrNull() ?: 5000L,
                sqsMaxMessages = System.getenv("SQS_MAX_MESSAGES")?.toIntOrNull() ?: 10,
                sqsWaitTimeSeconds = System.getenv("SQS_WAIT_TIME_SECONDS")?.toIntOrNull() ?: 20,
            )
        }
    }
}
