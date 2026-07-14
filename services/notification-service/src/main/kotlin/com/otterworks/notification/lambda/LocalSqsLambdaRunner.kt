package com.otterworks.notification.lambda

import aws.sdk.kotlin.services.sqs.SqsClient
import aws.sdk.kotlin.services.sqs.model.DeleteMessageRequest
import aws.sdk.kotlin.services.sqs.model.ReceiveMessageRequest
import aws.smithy.kotlin.runtime.net.url.Url
import com.amazonaws.services.lambda.runtime.events.SQSEvent
import com.otterworks.notification.config.AppConfig
import kotlinx.coroutines.runBlocking
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

/**
 * LOCAL STAND-IN for the AWS SQS -> Lambda event-source mapping.
 *
 * In real AWS the pipeline is EventBridge -> SQS -> Lambda, and the managed
 * event-source mapping (see infrastructure/terraform/modules/messaging-serverless-evt1
 * :: aws_lambda_event_source_mapping) polls SQS and invokes
 * [NotificationLambdaHandler]. That mapping cannot run on a laptop / in the
 * LocalStack Community image, so this tiny runner reproduces it: it long-polls
 * an SQS queue, wraps the batch into an [SQSEvent], and invokes the SAME
 * [NotificationLambdaHandler.handleRequest] used in production, deleting only
 * the records the handler reports as succeeded.
 *
 * It is a verification/dev tool (not deployed to AWS): it lets the repo's own
 * API-flow suite exercise the serverless consumer path end-to-end against
 * LocalStack, proving parity with the in-cluster consumer.
 *
 *   SQS_QUEUE_URL / AWS_ENDPOINT_URL / AWS_REGION are read from the same env as
 *   the service (AppConfig.load()).
 */
object LocalSqsLambdaRunner {
    @JvmStatic
    fun main(args: Array<String>) {
        val config = AppConfig.load()
        val handler = NotificationLambdaHandler()
        val sqs = SqsClient {
            region = config.awsRegion
            config.awsEndpointUrl?.let { endpointUrl = Url.parse(it) }
        }

        logger.info { "LocalSqsLambdaRunner draining ${config.sqsQueueUrl} (serverless Lambda stand-in)" }

        Runtime.getRuntime().addShutdownHook(Thread { runBlocking { sqs.close() } })

        runBlocking {
            while (true) {
                val response = sqs.receiveMessage(
                    ReceiveMessageRequest {
                        queueUrl = config.sqsQueueUrl
                        maxNumberOfMessages = config.sqsMaxMessages
                        waitTimeSeconds = config.sqsWaitTimeSeconds
                    },
                )
                val messages = response.messages ?: emptyList()
                if (messages.isEmpty()) continue

                val event = SQSEvent()
                event.records = messages.map { m ->
                    SQSEvent.SQSMessage().apply {
                        messageId = m.messageId
                        body = m.body
                    }
                }

                val failed = handler.handleRequest(event, null)
                    .batchItemFailures.map { it.itemIdentifier }.toSet()

                for (m in messages) {
                    if (m.messageId !in failed) {
                        sqs.deleteMessage(
                            DeleteMessageRequest {
                                queueUrl = config.sqsQueueUrl
                                receiptHandle = m.receiptHandle
                            },
                        )
                    }
                }
            }
        }
    }
}
