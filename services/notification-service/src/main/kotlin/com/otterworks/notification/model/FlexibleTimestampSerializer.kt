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
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Accepts both RFC 3339 strings ("2024-01-01T00:00:00Z") and
 * Unix epoch integers (1704067200) and normalizes them to an
 * ISO-8601 string representation.
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
                val epochSeconds = element.content.toLongOrNull()
                    ?: return element.content
                Instant.ofEpochSecond(epochSeconds)
                    .let { DateTimeFormatter.ISO_INSTANT.format(it) }
            }
        }
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
