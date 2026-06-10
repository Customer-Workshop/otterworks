package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * Accepts both ISO-8601 strings ("2024-01-01T00:00:00Z") and Unix-epoch
 * integers (1704067200) and always produces an ISO-8601 string.  This makes
 * the consumer resilient to legacy messages that encode timestamps as numbers
 * regardless of whether the lenient or strict JSON parser is in use.
 */
object FlexibleTimestampSerializer : KSerializer<String> {
    private val isoFormatter: DateTimeFormatter =
        DateTimeFormatter.ISO_INSTANT.withZone(ZoneOffset.UTC)

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement().jsonPrimitive

        element.longOrNull?.let { epoch ->
            return isoFormatter.format(Instant.ofEpochSecond(epoch))
        }

        return element.content
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
