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
 * Handles both RFC 3339 string timestamps (e.g. "2024-01-01T00:00:00Z")
 * and legacy Unix epoch integer timestamps (e.g. 1704067200).
 * Epoch integers are converted to ISO-8601 strings for downstream consistency.
 */
object FlexibleTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement().jsonPrimitive

        return if (element.isString) {
            element.content
        } else {
            val epoch = element.long
            Instant.ofEpochSecond(epoch).let { DateTimeFormatter.ISO_INSTANT.format(it) }
        }
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
