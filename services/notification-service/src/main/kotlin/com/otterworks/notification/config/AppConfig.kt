package com.otterworks.notification.config

data class AppConfig(
    val port: Int,
    val awsRegion: String,
    val awsEndpointUrl: String?,
    val sqsQueueUrl: String,
    val snsTopicArn: String,
    val dynamoDbTable: String,
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
                dynamoDbTable = System.getenv("DYNAMODB_TABLE") ?: "otterworks-notifications",
            )
        }
    }
}
