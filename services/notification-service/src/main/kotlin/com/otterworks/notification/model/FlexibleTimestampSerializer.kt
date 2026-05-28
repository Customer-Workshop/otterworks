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
 * Serializer that accepts both RFC 3339 timestamp strings (e.g. "2024-01-01T00:00:00Z")
 * and Unix epoch integers (e.g. 1704067200). Legacy event producers emit epoch integers,
 * while newer producers emit ISO 8601 / RFC 3339 strings. This serializer normalizes
 * both formats to an ISO 8601 string on deserialization.
 */
object FlexibleTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement() as? JsonPrimitive
            ?: return ""

        val epochValue = element.longOrNull
        if (epochValue != null) {
            return Instant.ofEpochSecond(epochValue)
                .atOffset(java.time.ZoneOffset.UTC)
                .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        }

        return element.content
    }
}
