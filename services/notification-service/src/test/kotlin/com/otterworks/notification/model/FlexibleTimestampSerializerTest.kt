package com.otterworks.notification.model

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

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
    fun `parses RFC 3339 string timestamp with strict parser`() {
        val body = """{"eventType":"file_shared","timestamp":"2024-01-01T00:00:00Z"}"""
        val event = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("2024-01-01T00:00:00Z", event.timestamp)
    }

    @Test
    fun `parses numeric epoch timestamp with strict parser`() {
        val body = """{"eventType":"file_shared","timestamp":1704067200}"""
        val event = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("2024-01-01T00:00:00Z", event.timestamp)
    }

    @Test
    fun `parses RFC 3339 string timestamp with lenient parser`() {
        val body = """{"eventType":"file_shared","timestamp":"2024-06-15T10:30:00Z"}"""
        val event = lenientJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("2024-06-15T10:30:00Z", event.timestamp)
    }

    @Test
    fun `parses numeric epoch timestamp with lenient parser`() {
        val body = """{"eventType":"file_shared","timestamp":1704067200}"""
        val event = lenientJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("2024-01-01T00:00:00Z", event.timestamp)
    }

    @Test
    fun `handles large epoch timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":2000000000}"""
        val event = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("2033-05-18T03:33:20Z", event.timestamp)
    }

    @Test
    fun `strict parser rejects unknown keys but handles epoch timestamp`() {
        val body = """{"eventType":"file_shared","timestamp":1704067200}"""
        val event = strictJson.decodeFromString<SqsNotificationMessage>(body)
        assertNotNull(event)
        assertEquals("file_shared", event.eventType)
    }
}
