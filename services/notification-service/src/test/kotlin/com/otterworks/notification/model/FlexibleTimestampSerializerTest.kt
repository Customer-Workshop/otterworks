package com.otterworks.notification.model

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals

class FlexibleTimestampSerializerTest {

    private val strictJson = Json {
        ignoreUnknownKeys = false
        isLenient = false
    }

    private val lenientJson = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    @Test
    fun `strict parser accepts ISO-8601 string timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":"2024-01-01T00:00:00Z"}"""
        val msg = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertEquals("2024-01-01T00:00:00Z", msg.timestamp)
    }

    @Test
    fun `strict parser accepts epoch integer timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":1704067200}"""
        val msg = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertEquals("2024-01-01T00:00:00Z", msg.timestamp)
    }

    @Test
    fun `lenient parser accepts ISO-8601 string timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":"2024-06-15T10:30:00Z"}"""
        val msg = lenientJson.decodeFromString<SqsNotificationMessage>(body)
        assertEquals("2024-06-15T10:30:00Z", msg.timestamp)
    }

    @Test
    fun `lenient parser accepts epoch integer timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":1704067200}"""
        val msg = lenientJson.decodeFromString<SqsNotificationMessage>(body)
        assertEquals("2024-01-01T00:00:00Z", msg.timestamp)
    }

    @Test
    fun `serializer round-trips ISO-8601 string`() {
        val original = SqsNotificationMessage(eventType = "file_shared", timestamp = "2024-01-01T00:00:00Z")
        val json = strictJson.encodeToString(SqsNotificationMessage.serializer(), original)
        val decoded = strictJson.decodeFromString<SqsNotificationMessage>(json)
        assertEquals(original.timestamp, decoded.timestamp)
    }
}
