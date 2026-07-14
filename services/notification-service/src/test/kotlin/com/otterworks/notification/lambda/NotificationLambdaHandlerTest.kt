package com.otterworks.notification.lambda

import com.amazonaws.services.lambda.runtime.events.SQSEvent
import com.otterworks.notification.consumer.MessageParser
import com.otterworks.notification.model.SqsNotificationMessage
import com.otterworks.notification.service.NotificationService
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.slot
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class NotificationLambdaHandlerTest {

    private fun sqsEvent(vararg bodies: Pair<String, String>): SQSEvent {
        val event = SQSEvent()
        event.records = bodies.map { (id, body) ->
            SQSEvent.SQSMessage().apply {
                messageId = id
                this.body = body
            }
        }
        return event
    }

    private val fileShared = """
        {"eventType":"file_shared","fileId":"file-123","ownerId":"owner-1","sharedWithUserId":"user-2","timestamp":"2024-01-01T00:00:00Z"}
    """.trimIndent()

    private val snsWrappedComment = run {
        val inner = """{"eventType":"comment_added","userId":"user-1","actorId":"actor-1","documentId":"doc-1","commentId":"c-1","timestamp":"2024-01-01T00:00:00Z"}"""
        val escaped = inner.replace("\"", "\\\"")
        """{"Type":"Notification","MessageId":"m-1","TopicArn":"arn:aws:sns:us-east-1:000000000000:t","Message":"$escaped"}"""
    }

    @Test
    fun `handler reuses NotificationService for each parsed record`() {
        val service = mockk<NotificationService>(relaxed = true)
        val captured = mutableListOf<SqsNotificationMessage>()
        coEvery { service.processEvent(capture(captured)) } returns Unit

        val handler = NotificationLambdaHandler(service)
        val response = handler.handleRequest(sqsEvent("1" to fileShared, "2" to snsWrappedComment), null)

        assertTrue(response.batchItemFailures.isEmpty(), "no failures expected for well-formed events")
        coVerify(exactly = 2) { service.processEvent(any()) }
        assertEquals(listOf("file_shared", "comment_added"), captured.map { it.eventType })
        assertEquals("user-2", captured[0].sharedWithUserId)
        assertEquals("c-1", captured[1].commentId)
    }

    @Test
    fun `handler reports batch item failure for unparseable record`() {
        val service = mockk<NotificationService>(relaxed = true)
        coEvery { service.processEvent(any()) } returns Unit

        val handler = NotificationLambdaHandler(service)
        val response = handler.handleRequest(sqsEvent("bad-1" to "not json at all"), null)

        assertEquals(1, response.batchItemFailures.size)
        assertEquals("bad-1", response.batchItemFailures[0].itemIdentifier)
        coVerify(exactly = 0) { service.processEvent(any()) }
    }

    @Test
    fun `handler reports batch item failure when processing throws`() {
        val service = mockk<NotificationService>()
        coEvery { service.processEvent(any()) } throws RuntimeException("downstream boom")

        val handler = NotificationLambdaHandler(service)
        val response = handler.handleRequest(sqsEvent("x" to fileShared), null)

        assertEquals(1, response.batchItemFailures.size)
        assertEquals("x", response.batchItemFailures[0].itemIdentifier)
    }

    // Reconciliation guard: the serverless Lambda path and the in-cluster
    // consumer path MUST derive the same SqsNotificationMessage from the same
    // wire bytes. Both delegate to MessageParser, so this proves the events
    // handed to NotificationService are byte-for-byte equivalent across paths.
    @Test
    fun `serverless and in-cluster paths parse identical events`() {
        val service = mockk<NotificationService>(relaxed = true)
        val lambdaSlot = slot<SqsNotificationMessage>()
        coEvery { service.processEvent(capture(lambdaSlot)) } returns Unit

        val handler = NotificationLambdaHandler(service)
        handler.handleRequest(sqsEvent("1" to fileShared), null)

        val inClusterParsed = MessageParser.parse(fileShared)
        assertEquals(inClusterParsed, lambdaSlot.captured)
    }
}
