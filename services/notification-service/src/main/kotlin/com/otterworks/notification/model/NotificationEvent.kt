package com.otterworks.notification.model

import kotlinx.serialization.Serializable

@Serializable
data class NotificationEvent(
    val eventType: String,       // file_shared, comment_added, document_edited, user_mentioned
    val sourceService: String,   // file-service, document-service, collab-service
    val userId: String,          // Target user ID
    val actorId: String,         // User who triggered the event
    val resourceId: String,      // File/document/comment ID
    val resourceType: String,    // file, document, comment
    val title: String,
    val message: String,
    val metadata: Map<String, String> = emptyMap(),
    val timestamp: String,
)

@Serializable
data class Notification(
    val id: String,
    val userId: String,
    val type: String,
    val title: String,
    val message: String,
    val resourceId: String,
    val resourceType: String,
    val actorId: String,
    val read: Boolean = false,
    val deliveredVia: List<String> = emptyList(), // email, in_app, webhook
    val createdAt: String,
)

@Serializable
enum class DeliveryChannel {
    EMAIL,
    IN_APP,
    WEBHOOK,
}
