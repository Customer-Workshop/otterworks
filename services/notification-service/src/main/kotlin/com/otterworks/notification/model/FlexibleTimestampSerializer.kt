package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Accepts both ISO-8601 / RFC 3339 strings and Unix epoch integers (seconds),
 * normalising the latter to an ISO-8601 UTC string so downstream code always
 * receives a consistent format.
 */
object FlexibleTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement() as? JsonPrimitive
            ?: return ""

        val epochValue = element.longOrNull
        if (epochValue != null) {
            val instant = if (epochValue > 1_000_000_000_000L) {
                Instant.ofEpochMilli(epochValue)
            } else {
                Instant.ofEpochSecond(epochValue)
            }
            return DateTimeFormatter.ISO_INSTANT.format(instant)
        }

        return element.content
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
