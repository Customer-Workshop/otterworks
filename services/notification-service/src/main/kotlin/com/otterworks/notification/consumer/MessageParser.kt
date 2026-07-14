package com.otterworks.notification.consumer

import com.otterworks.notification.model.SqsNotificationMessage
import kotlinx.serialization.json.Json
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

/**
 * Shared domain-event parsing used by BOTH delivery paths:
 *   - the in-cluster [SqsConsumer] (SNS -> SQS, the golden before-state), and
 *   - the serverless [com.otterworks.notification.lambda.NotificationLambdaHandler]
 *     (EventBridge -> SQS -> Lambda, the re-architected path).
 *
 * Keeping a single parser is what makes the two paths behavior-identical: the
 * same lenient/strict handling, the same SNS-envelope unwrapping, and the same
 * chaos hook. The re-architecture is an adapter swap, not a parsing rewrite.
 */
object MessageParser {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    // CHAOS parser (planted-bug mechanism, left intact): rejects messages whose
    // timestamp is not RFC 3339 when the chaos flag is active. Shared so the
    // serverless path exhibits the SAME behavior as the in-cluster consumer.
    private val strictJson = Json {
        ignoreUnknownKeys = false
        isLenient = false
    }

    fun parse(body: String, chaosStrict: Boolean = false): SqsNotificationMessage? {
        val parser = if (chaosStrict) strictJson else json
        return try {
            parser.decodeFromString<SqsNotificationMessage>(body)
        } catch (_: Exception) {
            try {
                val snsWrapper = parser.decodeFromString<SnsEnvelope>(body)
                parser.decodeFromString<SqsNotificationMessage>(snsWrapper.Message)
            } catch (e: Exception) {
                logger.error(e) { "Failed to parse message body" }
                null
            }
        }
    }
}
