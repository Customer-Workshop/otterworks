package com.otterworks.notification.consumer

import aws.sdk.kotlin.services.sqs.SqsClient
import aws.sdk.kotlin.services.sqs.model.DeleteMessageRequest
import aws.sdk.kotlin.services.sqs.model.ReceiveMessageRequest
import com.otterworks.notification.config.AppConfig
import com.otterworks.notification.model.DocumentServiceEnvelope
import com.otterworks.notification.model.SqsNotificationMessage
import com.otterworks.notification.service.NotificationService
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
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

                            // Always delete processed or unparseable messages to prevent
                            // queue poisoning from schema-incompatible messages
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
            // Try parsing as direct message first
            val parsed = json.decodeFromString<SqsNotificationMessage>(body)
            parsed.copy(eventType = normalizeEventType(parsed.eventType))
        } catch (_: Exception) {
            try {
                // Try unwrapping SNS envelope
                val snsWrapper = json.decodeFromString<SnsEnvelope>(body)
                parseInnerMessage(snsWrapper.Message)
            } catch (e: Exception) {
                logger.error(e) { "Failed to parse message body" }
                null
            }
        }
    }

    internal fun parseInnerMessage(message: String): SqsNotificationMessage? {
        return try {
            val jsonObj = json.parseToJsonElement(message).jsonObject

            if ("payload" in jsonObj) {
                // Document-service format: {event_type, timestamp, payload: {...}}
                val envelope = json.decodeFromString<DocumentServiceEnvelope>(message)
                if (envelope.eventType.isBlank()) return null
                convertEnvelopeToMessage(envelope)
            } else {
                // Flat notification message (file-service, etc.)
                val parsed = json.decodeFromString<SqsNotificationMessage>(message)
                parsed.copy(eventType = normalizeEventType(parsed.eventType))
            }
        } catch (e: Exception) {
            logger.error(e) { "Failed to parse inner message" }
            null
        }
    }

    private fun convertEnvelopeToMessage(envelope: DocumentServiceEnvelope): SqsNotificationMessage {
        val payload = envelope.payload
        fun payloadString(key: String): String =
            (payload[key] as? JsonPrimitive)?.contentOrNull ?: ""

        return SqsNotificationMessage(
            eventType = normalizeEventType(envelope.eventType),
            timestamp = envelope.timestamp,
            documentId = payloadString("document_id").ifEmpty { payloadString("id") },
            commentId = payloadString("comment_id"),
            userId = payloadString("owner_id").ifEmpty { payloadString("author_id") },
            actorId = payloadString("author_id"),
            ownerId = payloadString("owner_id"),
            fileId = payloadString("file_id"),
            sharedWithUserId = payloadString("shared_with_user_id"),
            mentionedUserId = payloadString("mentioned_user_id"),
        )
    }

    private fun normalizeEventType(raw: String): String {
        return when (raw) {
            "document_updated" -> "document_edited"
            "document_created" -> "document_edited"
            else -> raw
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
