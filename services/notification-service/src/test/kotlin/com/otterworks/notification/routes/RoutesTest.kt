package com.otterworks.notification.routes

import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.put
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.testing.ApplicationTestBuilder
import io.ktor.server.testing.testApplication
import io.ktor.server.websocket.WebSockets
import io.micrometer.prometheus.PrometheusConfig
import io.micrometer.prometheus.PrometheusMeterRegistry
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import org.koin.core.context.stopKoin as stopKoinContext
import org.koin.dsl.module
import org.koin.ktor.plugin.Koin
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals

class RoutesTest {

    @AfterTest
    fun stopKoin() {
        stopKoinContext()
    }

    @Test
    fun `GET notifications without user id returns bad request`() = testApplication {
        installRoutes()

        val response = client.get("/api/v1/notifications")

        assertEquals(HttpStatusCode.BadRequest, response.status)
        assertEquals(
            """{"error":"user_id is required (via X-User-ID header or query parameter)"}""",
            response.bodyAsText(),
        )
    }

    @Test
    fun `GET unread count with user id returns count and calls service`() = testApplication {
        val service = mockk<NotificationService>(relaxed = true)
        coEvery { service.getUnreadCount("user-1") } returns 3
        installRoutes(service)

        val response = client.get("/api/v1/notifications/unread-count") {
            header("X-User-ID", "user-1")
        }

        assertEquals(HttpStatusCode.OK, response.status)
        coVerify { service.getUnreadCount("user-1") }
    }

    @Test
    fun `PUT mark as read returns not found when service returns false`() = testApplication {
        val service = mockk<NotificationService>(relaxed = true)
        coEvery { service.markAsRead("notification-1") } returns false
        installRoutes(service)

        val response = client.put("/api/v1/notifications/notification-1/read")

        assertEquals(HttpStatusCode.NotFound, response.status)
    }

    @Test
    fun `PUT mark as read returns no content when service returns true`() = testApplication {
        val service = mockk<NotificationService>(relaxed = true)
        coEvery { service.markAsRead("notification-1") } returns true
        installRoutes(service)

        val response = client.put("/api/v1/notifications/notification-1/read")

        assertEquals(HttpStatusCode.NoContent, response.status)
    }

    @Test
    fun `GET health returns ok`() = testApplication {
        installRoutes()

        val response = client.get("/health")

        assertEquals(HttpStatusCode.OK, response.status)
    }

    private fun ApplicationTestBuilder.installRoutes(
        service: NotificationService = mockk(relaxed = true),
        webSocketManager: WebSocketManager = mockk(relaxed = true),
    ) {
        application {
            install(ContentNegotiation) {
                json()
            }
            install(WebSockets)
            install(Koin) {
                modules(module {
                    single { service }
                    single { webSocketManager }
                })
            }
            configureRouting(PrometheusMeterRegistry(PrometheusConfig.DEFAULT))
        }
    }
}
