package com.otterworks.notification.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
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
 * Event timestamps arrive either as RFC 3339 strings (current producers) or as Unix epoch
 * numbers in seconds or milliseconds (legacy producers). Both decode to an ISO-8601 UTC string.
 */
object EventTimestampSerializer : KSerializer<String> {
    private const val EPOCH_MILLIS_THRESHOLD = 100_000_000_000L

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("com.otterworks.notification.EventTimestamp", PrimitiveKind.STRING)

    override fun serialize(encoder: Encoder, value: String) = encoder.encodeString(value)

    override fun deserialize(decoder: Decoder): String {
        val jsonDecoder = decoder as? JsonDecoder ?: return decoder.decodeString()
        val element = jsonDecoder.decodeJsonElement() as? JsonPrimitive
            ?: throw SerializationException("timestamp must be a string or a number")
        if (element.isString) return element.content
        val epoch = element.longOrNull
            ?: throw SerializationException("timestamp must be an RFC 3339 string or an integer epoch, got ${element.content}")
        return fromEpoch(epoch)
    }

    fun fromEpoch(epoch: Long): String {
        val instant = if (epoch >= EPOCH_MILLIS_THRESHOLD) Instant.ofEpochMilli(epoch) else Instant.ofEpochSecond(epoch)
        return instant.toString()
    }
}

@Serializable
enum class EventType {
    file_shared,
    comment_added,
    document_edited,
    user_mentioned;

    companion object {
        fun fromString(value: String): EventType? = entries.find { it.name == value }
    }
}

@Serializable
data class NotificationEvent(
    val eventType: String,
    val sourceService: String = "",
    val userId: String,
    val actorId: String = "",
    val resourceId: String = "",
    val resourceType: String = "",
    val title: String = "",
    val message: String = "",
    val metadata: Map<String, String> = emptyMap(),
    @Serializable(with = EventTimestampSerializer::class)
    val timestamp: String,
)

@Serializable
data class SqsNotificationMessage(
    val eventType: String,
    val fileId: String = "",
    val ownerId: String = "",
    val sharedWithUserId: String = "",
    val documentId: String = "",
    val commentId: String = "",
    val userId: String = "",
    val actorId: String = "",
    val mentionedUserId: String = "",
    @Serializable(with = EventTimestampSerializer::class)
    val timestamp: String,
)

@Serializable
data class Notification(
    val id: String,
    val userId: String,
    val type: String,
    val title: String,
    val message: String,
    val resourceId: String = "",
    val resourceType: String = "",
    val actorId: String = "",
    val read: Boolean = false,
    val deliveredVia: List<String> = emptyList(),
    val createdAt: String,
)

@Serializable
enum class DeliveryChannel {
    EMAIL,
    IN_APP,
    PUSH;
}

@Serializable
data class NotificationPreference(
    val userId: String,
    val channels: Map<String, List<DeliveryChannel>> = mapOf(
        "file_shared" to listOf(DeliveryChannel.EMAIL, DeliveryChannel.IN_APP, DeliveryChannel.PUSH),
        "comment_added" to listOf(DeliveryChannel.IN_APP, DeliveryChannel.PUSH),
        "document_edited" to listOf(DeliveryChannel.IN_APP),
        "user_mentioned" to listOf(DeliveryChannel.EMAIL, DeliveryChannel.IN_APP, DeliveryChannel.PUSH),
    ),
)

@Serializable
data class PaginatedResponse<T>(
    val data: List<T>,
    val total: Int,
    val page: Int,
    val pageSize: Int,
    val hasMore: Boolean,
)

@Serializable
data class UnreadCountResponse(
    val userId: String,
    val unreadCount: Int,
)

@Serializable
data class NotificationPreferenceRequest(
    val userId: String,
    val eventType: String,
    val channels: List<DeliveryChannel>,
)
