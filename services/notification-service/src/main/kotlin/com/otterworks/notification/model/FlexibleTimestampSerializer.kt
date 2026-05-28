package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import java.time.format.DateTimeFormatter

object FlexibleTimestampSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("FlexibleTimestamp", PrimitiveKind.STRING)

    override fun serialize(encoder: Encoder, value: String) {
        encoder.encodeString(value)
    }

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return decoder.decodeString()

        val element = jsonDecoder.decodeJsonElement()
        if (element !is JsonPrimitive) {
            throw SerializationException("Expected string or number for timestamp, got: $element")
        }

        if (element.isString) {
            return element.content
        }

        val epochSeconds = element.content.toLongOrNull()
            ?: throw SerializationException("Non-numeric timestamp value: ${element.content}")

        return Instant.ofEpochSecond(epochSeconds)
            .atOffset(java.time.ZoneOffset.UTC)
            .format(DateTimeFormatter.ISO_INSTANT)
    }
}
