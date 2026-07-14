package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.jsonPrimitive
import java.time.Instant

/**
 * Deserializes an event timestamp that may arrive either as an RFC 3339 string
 * (current producers) or as a Unix epoch integer in seconds or milliseconds
 * (legacy producers). The value is normalized to an ISO-8601 string so that
 * downstream code always sees a single canonical format and strict JSON parsing
 * does not reject numeric timestamps.
 */
object LenientTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("Timestamp", PrimitiveKind.STRING)

    // Epoch values at/above this magnitude are treated as milliseconds, below as
    // seconds. 10^12 s is ~year 33658 and 10^12 ms is ~year 2001, so this cleanly
    // separates second- from millisecond-precision epochs for realistic dates.
    private const val MILLIS_THRESHOLD = 1_000_000_000_000L

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder ?: return decoder.decodeString()
        val primitive = jsonDecoder.decodeJsonElement().jsonPrimitive
        if (primitive.isString) {
            return primitive.content
        }
        val epoch = primitive.content.toLongOrNull() ?: return primitive.content
        val instant = if (epoch >= MILLIS_THRESHOLD) {
            Instant.ofEpochMilli(epoch)
        } else {
            Instant.ofEpochSecond(epoch)
        }
        return instant.toString()
    }

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }
}
