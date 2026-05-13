package com.otterworks.notification.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonNames

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
    val timestamp: String,
)

@Serializable
data class SqsNotificationMessage(
    @JsonNames("event_type")
    val eventType: String,
    @JsonNames("file_id")
    val fileId: String = "",
    @JsonNames("owner_id")
    val ownerId: String = "",
    @JsonNames("shared_with_user_id")
    val sharedWithUserId: String = "",
    @JsonNames("document_id")
    val documentId: String = "",
    @JsonNames("comment_id")
    val commentId: String = "",
    @JsonNames("user_id")
    val userId: String = "",
    @JsonNames("actor_id")
    val actorId: String = "",
    @JsonNames("mentioned_user_id")
    val mentionedUserId: String = "",
    val timestamp: String = "",
)

@Serializable
internal data class DocumentServiceEnvelope(
    @JsonNames("event_type")
    val eventType: String = "",
    val timestamp: String = "",
    val payload: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
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
