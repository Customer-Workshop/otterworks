package com.otterworks.notification.routes

import com.otterworks.notification.model.DeliveryChannel
import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.ktor.client.request.header
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.testing.ApplicationTestBuilder
import io.ktor.server.testing.testApplication
import io.ktor.server.websocket.WebSockets
import io.micrometer.prometheus.PrometheusConfig
import io.micrometer.prometheus.PrometheusMeterRegistry
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.serialization.json.Json
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.koin.ktor.plugin.Koin
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals

class PreferencesRouteTest {

    private val notificationService = mockk<NotificationService>(relaxed = true)
    private val webSocketManager = mockk<WebSocketManager>(relaxed = true)

    @AfterTest
    fun tearDown() {
        stopKoin()
    }

    private fun ApplicationTestBuilder.setupApp() {
        application {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            install(WebSockets)
            install(Koin) {
                modules(
                    module {
                        single { notificationService }
                        single { webSocketManager }
                    }
                )
            }
            configureRouting(PrometheusMeterRegistry(PrometheusConfig.DEFAULT))
        }
    }

    @Test
    fun `PUT preferences uses the authenticated X-User-ID, not the body userId`() = testApplication {
        setupApp()

        val response = client.put("/api/v1/preferences") {
            header("X-User-ID", "alice")
            contentType(ContentType.Application.Json)
            setBody("""{"eventType":"file_shared","channels":["IN_APP"]}""")
        }

        assertEquals(HttpStatusCode.NoContent, response.status)
        coVerify(exactly = 1) { notificationService.updatePreferences("alice", "file_shared", listOf(DeliveryChannel.IN_APP)) }
    }

    @Test
    fun `PUT preferences rejects a body userId that differs from the caller`() = testApplication {
        setupApp()

        val response = client.put("/api/v1/preferences") {
            header("X-User-ID", "attacker")
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"victim","eventType":"file_shared","channels":[]}""")
        }

        assertEquals(HttpStatusCode.Forbidden, response.status)
        coVerify(exactly = 0) { notificationService.updatePreferences(any(), any(), any()) }
    }

    @Test
    fun `PUT preferences accepts a body userId that matches the caller`() = testApplication {
        setupApp()

        val response = client.put("/api/v1/preferences") {
            header("X-User-ID", "alice")
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"alice","eventType":"comment_added","channels":["EMAIL"]}""")
        }

        assertEquals(HttpStatusCode.NoContent, response.status)
        coVerify(exactly = 1) { notificationService.updatePreferences("alice", "comment_added", listOf(DeliveryChannel.EMAIL)) }
    }

    @Test
    fun `PUT preferences without an authenticated identity is rejected`() = testApplication {
        setupApp()

        val response = client.put("/api/v1/preferences") {
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"victim","eventType":"file_shared","channels":[]}""")
        }

        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.updatePreferences(any(), any(), any()) }
    }
}
