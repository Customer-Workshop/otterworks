package com.otterworks.notification.consumer

import aws.sdk.kotlin.services.sqs.SqsClient
import aws.sdk.kotlin.services.sqs.model.DeleteMessageRequest
import aws.sdk.kotlin.services.sqs.model.ReceiveMessageRequest
import com.otterworks.notification.config.AppConfig
import com.otterworks.notification.model.SqsNotificationMessage
import com.otterworks.notification.service.NotificationService
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

class SqsConsumer(
    private val sqsClient: SqsClient,
    private val notificationService: NotificationService,
    private val config: AppConfig,
) {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    suspend fun startPolling() = coroutineScope {
        logger.info { "Starting SQS consumer polling: ${config.sqsQueueUrl}" }

        while (isActive) {
            try {
                val request = ReceiveMessageRequest {
                    queueUrl = config.sqsQueueUrl
                    maxNumberOfMessages = config.sqsMaxMessages
                    waitTimeSeconds = config.sqsWaitTimeSeconds
                }

                val response = sqsClient.receiveMessage(request)
                val messages = response.messages ?: emptyList()

                if (messages.isNotEmpty()) {
                    logger.info { "Received ${messages.size} messages from SQS" }
                }

                for (msg in messages) {
                    launch {
                        try {
                            val body = msg.body ?: return@launch
                            val event = parseMessage(body)

                            if (event != null) {
                                notificationService.processEvent(event)
                            } else {
                                logger.warn { "Skipping unparseable SQS message: ${msg.messageId}" }
                            }

                            val deleteRequest = DeleteMessageRequest {
                                queueUrl = config.sqsQueueUrl
                                receiptHandle = msg.receiptHandle
                            }
                            sqsClient.deleteMessage(deleteRequest)
                            logger.debug { "Deleted SQS message: ${msg.messageId}" }
                        } catch (e: Exception) {
                            logger.error(e) { "Error processing SQS message: ${msg.messageId}" }
                        }
                    }
                }

                if (messages.isEmpty()) {
                    delay(config.sqsPollIntervalMs)
                }
            } catch (e: Exception) {
                logger.error(e) { "Error polling SQS" }
                delay(config.sqsPollIntervalMs * 2)
            }
        }
    }

    internal fun parseMessage(body: String): SqsNotificationMessage? {
        return try {
            json.decodeFromString<SqsNotificationMessage>(body)
        } catch (_: Exception) {
            try {
                val snsWrapper = json.decodeFromString<SnsEnvelope>(body)
                parseInnerMessage(snsWrapper.Message)
            } catch (e: Exception) {
                logger.error(e) { "Failed to parse message body" }
                null
            }
        }
    }

    internal fun parseInnerMessage(inner: String): SqsNotificationMessage? {
        return try {
            json.decodeFromString<SqsNotificationMessage>(inner)
        } catch (_: Exception) {
            tryParseSnakeCaseMessage(inner)
        }
    }

    private fun tryParseSnakeCaseMessage(inner: String): SqsNotificationMessage? {
        return try {
            val obj = json.parseToJsonElement(inner).jsonObject
            val eventType = obj["event_type"]?.jsonPrimitive?.content ?: return null
            val timestamp = obj["timestamp"]?.jsonPrimitive?.content ?: return null
            val payload = (obj["payload"] as? JsonObject) ?: JsonObject(emptyMap())

            SqsNotificationMessage(
                eventType = eventType,
                fileId = payload["file_id"]?.jsonPrimitive?.content ?: "",
                ownerId = payload["owner_id"]?.jsonPrimitive?.content ?: "",
                sharedWithUserId = payload["shared_with_user_id"]?.jsonPrimitive?.content ?: "",
                documentId = payload["document_id"]?.jsonPrimitive?.content ?: "",
                commentId = payload["comment_id"]?.jsonPrimitive?.content ?: "",
                userId = payload["user_id"]?.jsonPrimitive?.content
                    ?: payload["author_id"]?.jsonPrimitive?.content ?: "",
                actorId = payload["actor_id"]?.jsonPrimitive?.content ?: "",
                mentionedUserId = payload["mentioned_user_id"]?.jsonPrimitive?.content ?: "",
                timestamp = timestamp,
            )
        } catch (e: Exception) {
            logger.error(e) { "Failed to parse snake_case message" }
            null
        }
    }
}

@kotlinx.serialization.Serializable
internal data class SnsEnvelope(
    val Message: String,
    val MessageId: String = "",
    val TopicArn: String = "",
    val Type: String = "",
)
