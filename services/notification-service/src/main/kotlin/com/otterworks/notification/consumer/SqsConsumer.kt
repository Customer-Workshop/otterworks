package com.otterworks.notification.consumer

import com.otterworks.notification.config.AppConfig
import kotlinx.coroutines.delay
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

class SqsConsumer(private val config: AppConfig) {

    suspend fun startPolling() {
        logger.info { "Starting SQS consumer polling: ${config.sqsQueueUrl}" }

        while (true) {
            try {
                // TODO: Implement SQS long polling with AWS SDK
                // 1. Receive messages from SQS queue
                // 2. Parse event type (file_shared, comment_added, document_edited, etc.)
                // 3. Route to appropriate handler
                // 4. Deliver notification (email via SES, in-app via WebSocket, webhook)
                // 5. Store notification in DynamoDB
                // 6. Delete processed message from SQS

                delay(5000) // Poll every 5 seconds
            } catch (e: Exception) {
                logger.error(e) { "Error polling SQS" }
                delay(10000) // Back off on error
            }
        }
    }
}
