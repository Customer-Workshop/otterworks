package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Serializer that accepts timestamps in both ISO 8601 string format
 * (e.g. "2024-01-01T00:00:00Z") and numeric Unix epoch format
 * (e.g. 1704067200 or 1704067200000). This allows the notification
 * consumer to process both legacy messages (epoch integers) and
 * current messages (RFC 3339 strings) without deserialization failures.
 */
object FlexibleTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement().jsonPrimitive

        return when {
            element.isString -> element.content
            else -> {
                val epochValue = element.long
                val instant = if (epochValue > 1_000_000_000_000L) {
                    Instant.ofEpochMilli(epochValue)
                } else {
                    Instant.ofEpochSecond(epochValue)
                }
                DateTimeFormatter.ISO_INSTANT.format(instant)
            }
        }
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
