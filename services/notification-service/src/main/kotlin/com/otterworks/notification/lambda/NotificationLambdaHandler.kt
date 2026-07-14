package com.otterworks.notification.lambda

import aws.sdk.kotlin.services.dynamodb.DynamoDbClient
import aws.sdk.kotlin.services.ses.SesClient
import aws.smithy.kotlin.runtime.net.url.Url
import com.amazonaws.services.lambda.runtime.Context
import com.amazonaws.services.lambda.runtime.RequestHandler
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse
import com.amazonaws.services.lambda.runtime.events.SQSEvent
import com.otterworks.notification.config.AppConfig
import com.otterworks.notification.consumer.MessageParser
import com.otterworks.notification.repository.NotificationRepository
import com.otterworks.notification.service.EmailSender
import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import kotlinx.coroutines.runBlocking
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

/**
 * Serverless consumer for the re-architected notification pipeline:
 *
 *   domain event -> EventBridge bus -> rule -> SQS queue -> THIS Lambda
 *
 * It is the event-driven equivalent of the in-cluster
 * [com.otterworks.notification.consumer.SqsConsumer] poll loop. Crucially it
 * reuses the EXACT same building blocks — [MessageParser] for parsing and
 * [NotificationService.processEvent] for the notification behavior (preferences,
 * template rendering, DynamoDB persistence, email/push delivery) — so the
 * observable notification outcome is identical to the golden before-state. The
 * re-architecture is an adapter swap behind a config flip, not a logic rewrite.
 *
 * Returns [SQSBatchResponse] with per-message failures so unparseable/failed
 * records are retried and eventually dead-lettered (the SQS+DLQ redrive policy),
 * mirroring the at-least-once semantics of the in-cluster consumer.
 */
class NotificationLambdaHandler(
    private val notificationService: NotificationService = buildDefaultService(),
) : RequestHandler<SQSEvent, SQSBatchResponse> {

    override fun handleRequest(event: SQSEvent, context: Context?): SQSBatchResponse {
        val failures = mutableListOf<SQSBatchResponse.BatchItemFailure>()
        val records = event.records ?: emptyList()
        logger.info { "Lambda received ${records.size} SQS record(s)" }

        for (record in records) {
            try {
                val parsed = MessageParser.parse(record.body)
                if (parsed == null) {
                    logger.warn { "Failed to parse SQS record ${record.messageId}; sending to retry/DLQ" }
                    failures.add(SQSBatchResponse.BatchItemFailure(record.messageId))
                    continue
                }
                runBlocking { notificationService.processEvent(parsed) }
                logger.debug { "Processed SQS record ${record.messageId}" }
            } catch (e: Exception) {
                logger.error(e) { "Error processing SQS record ${record.messageId}; sending to retry/DLQ" }
                failures.add(SQSBatchResponse.BatchItemFailure(record.messageId))
            }
        }

        return SQSBatchResponse(failures)
    }

    companion object {
        // Cold-start-initialized dependencies, reused across warm invocations.
        // Mirrors the Koin wiring in Application.configureDependencyInjection so
        // the Lambda and the pod construct NotificationService identically.
        private fun buildDefaultService(): NotificationService {
            val config = AppConfig.load()

            val dynamoDb = DynamoDbClient {
                region = config.awsRegion
                config.awsEndpointUrl?.let { endpointUrl = Url.parse(it) }
            }
            val ses = SesClient {
                region = config.awsRegion
                config.awsEndpointUrl?.let { endpointUrl = Url.parse(it) }
            }

            return NotificationService(
                repository = NotificationRepository(dynamoDb, config),
                emailSender = EmailSender(ses, config),
                webSocketManager = WebSocketManager(),
                meterRegistry = null,
            )
        }
    }
}
