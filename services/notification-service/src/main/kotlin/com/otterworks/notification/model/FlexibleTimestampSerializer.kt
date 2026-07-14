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

/**
 * Deserializes an event timestamp that may arrive either as an RFC 3339 string
 * (current producers) or as a Unix epoch integer (legacy producers). Both forms
 * are normalized to an RFC 3339 string so the consumer accepts the message
 * regardless of which producer version emitted it and regardless of the JSON
 * parser's strictness.
 */
object FlexibleTimestampSerializer : KSerializer<String> {

    // Values at or above this bound are interpreted as epoch milliseconds;
    // smaller integers are treated as epoch seconds (~year 33658 in seconds).
    private const val EPOCH_MILLIS_THRESHOLD = 100_000_000_000L

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder ?: return decoder.decodeString()
        val primitive = jsonDecoder.decodeJsonElement() as? JsonPrimitive
            ?: return decoder.decodeString()

        if (primitive.isString) return primitive.content

        val epoch = primitive.longOrNull ?: return primitive.content
        val instant = if (epoch >= EPOCH_MILLIS_THRESHOLD) {
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
