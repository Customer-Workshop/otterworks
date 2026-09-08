package com.otterworks.notification.contract

import com.otterworks.notification.model.Notification
import com.otterworks.notification.model.NotificationPreference
import com.otterworks.notification.model.SqsNotificationMessage
import com.otterworks.notification.repository.NotificationRepository
import com.otterworks.notification.service.EmailSender
import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Verifies that the frame notification-service pushes over /ws/notifications/{userId}
 * conforms to shared/events/schemas/notification-events.json#/definitions/NotificationSentEvent.
 */
class NotificationEventContractTest {

    private val schema: JsonObject =
        JsonSchemaAssert.loadDefinition("notification-events.json", "NotificationSentEvent")

    private val repository = mockk<NotificationRepository>(relaxed = true)
    private val emailSender = mockk<EmailSender>(relaxed = true)
    private val webSocketManager = WebSocketManager()

    private val service = NotificationService(
        repository = repository,
        emailSender = emailSender,
        webSocketManager = mockk(relaxed = true),
        meterRegistry = null,
    )

    private val inboundEvents = listOf(
        SqsNotificationMessage(
            eventType = "file_shared",
            fileId = "file-123",
            ownerId = "owner-1",
            sharedWithUserId = "user-2",
            timestamp = "2024-01-01T00:00:00Z",
        ),
        SqsNotificationMessage(
            eventType = "comment_added",
            userId = "doc-owner",
            actorId = "commenter",
            documentId = "doc-1",
            commentId = "comment-1",
            timestamp = "2024-01-01T00:00:00Z",
        ),
        SqsNotificationMessage(
            eventType = "document_edited",
            userId = "doc-owner",
            actorId = "editor",
            documentId = "doc-1",
            timestamp = "2024-01-01T00:00:00Z",
        ),
        SqsNotificationMessage(
            eventType = "user_mentioned",
            mentionedUserId = "user-3",
            actorId = "actor-1",
            documentId = "doc-1",
            timestamp = "2024-01-01T00:00:00Z",
        ),
    )

    private suspend fun publishedFrame(event: SqsNotificationMessage): JsonObject {
        val targetUserId = NotificationService.resolveTargetUserId(event)
        coEvery { repository.getPreferences(targetUserId) } returns NotificationPreference(userId = targetUserId)
        coEvery { emailSender.sendEmail(any(), any(), any()) } returns true

        service.processEvent(event)

        val saved = mutableListOf<Notification>()
        coVerify(atLeast = 1) { repository.saveNotification(capture(saved)) }
        return Json.parseToJsonElement(webSocketManager.encode(saved.last())).jsonObject
    }

    @Test
    fun `every inbound event type produces a WebSocket frame that conforms to NotificationSentEvent`() = runTest {
        for (event in inboundEvents) {
            val frame = publishedFrame(event)
            JsonSchemaAssert.assertConformsTo(schema, frame)
            assertEquals("notification_sent", frame["eventType"]?.jsonPrimitive?.content, "eventType for ${event.eventType}")
        }
    }

    @Test
    fun `frame uses the consumer-facing notification type vocabulary`() = runTest {
        val expectedTypes = mapOf(
            "file_shared" to "share",
            "comment_added" to "comment",
            "document_edited" to "edit",
            "user_mentioned" to "mention",
        )
        for (event in inboundEvents) {
            val frame = publishedFrame(event)
            assertEquals(expectedTypes.getValue(event.eventType), frame["type"]?.jsonPrimitive?.content)
        }
    }

    @Test
    fun `frame only carries resourceType values the contract enumerates`() = runTest {
        val fileFrame = publishedFrame(inboundEvents.first { it.eventType == "file_shared" })
        assertEquals("file", fileFrame["resourceType"]?.jsonPrimitive?.content)
        assertEquals("file-123", fileFrame["resourceId"]?.jsonPrimitive?.content)

        val commentFrame = publishedFrame(inboundEvents.first { it.eventType == "comment_added" })
        assertFalse("resourceType" in commentFrame, "comment is not a routable resource type for clients")
    }

    @Test
    fun `frame always carries read flag and includes push in deliveredVia`() = runTest {
        val frame = publishedFrame(inboundEvents.first())
        assertEquals(false, frame.getValue("read").jsonPrimitive.content.toBoolean())
        val channels = frame.getValue("deliveredVia").jsonArray.map { it.jsonPrimitive.content }
        assertTrue("push" in channels, "deliveredVia=$channels")
        assertTrue("in_app" in channels, "deliveredVia=$channels")
    }

    @Test
    fun `serializing the persisted Notification record directly does not satisfy the contract`() {
        val record = Notification(
            id = "0f6a3a1e-4b3e-4a5b-9a4b-1f7e2c3d4e5f",
            userId = "user-2",
            type = "file_shared",
            title = "File Shared With You",
            message = "owner-1 shared a file",
            resourceId = "file-123",
            resourceType = "file",
            actorId = "owner-1",
            deliveredVia = listOf("in_app"),
            createdAt = "2024-01-01T00:00:00Z",
        )
        val legacyFrame = Json.parseToJsonElement(Json.encodeToString(record)).jsonObject

        val violations = JsonSchemaAssert.validate(schema, legacyFrame, "$")

        assertTrue(violations.any { "eventType" in it }, violations.toString())
        assertTrue(violations.any { it.startsWith("$.type") }, violations.toString())
        assertTrue(violations.any { "'read'" in it }, violations.toString())
    }
}
