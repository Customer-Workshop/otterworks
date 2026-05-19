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
 * Accepts both RFC 3339 string timestamps and Unix epoch integer timestamps,
 * normalising epoch values to ISO-8601 strings so downstream code always
 * receives a consistent format.
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

        val primitive = jsonDecoder.decodeJsonElement().jsonPrimitive

        if (primitive.isString) {
            return primitive.content
        }

        val epoch = primitive.content.toLongOrNull()
            ?: return primitive.content
        return Instant.ofEpochSecond(epoch).toString()
    }
}
