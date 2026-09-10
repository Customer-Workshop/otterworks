package com.otterworks.notification.routes

import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.put
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.testing.testApplication
import io.ktor.server.websocket.WebSockets
import io.micrometer.prometheus.PrometheusConfig
import io.micrometer.prometheus.PrometheusMeterRegistry
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.serialization.json.Json
import org.koin.dsl.module
import org.koin.ktor.plugin.Koin
import kotlin.test.Test
import kotlin.test.assertEquals

class RoutesTest {

    private val notificationService = mockk<NotificationService>()
    private val webSocketManager = mockk<WebSocketManager>(relaxed = true)

    private fun withRoutes(block: suspend io.ktor.server.testing.ApplicationTestBuilder.() -> Unit) = testApplication {
        application {
            install(ContentNegotiation) { json(Json) }
            install(WebSockets)
            install(Koin) {
                modules(
                    module {
                        single { notificationService }
                        single { webSocketManager }
                    },
                )
            }
            configureRouting(PrometheusMeterRegistry(PrometheusConfig.DEFAULT))
        }
        block()
    }

    @Test
    fun `missing notification yields the shared not-found error on every id route`() {
        coEvery { notificationService.getNotificationById("missing") } returns null
        coEvery { notificationService.markAsRead("missing") } returns false
        coEvery { notificationService.deleteNotification("missing") } returns false

        withRoutes {
            val expected = Json.encodeToString(ErrorResponse.serializer(), ErrorResponse(NOTIFICATION_NOT_FOUND))

            val get = client.get("/api/v1/notifications/missing")
            assertEquals(HttpStatusCode.NotFound, get.status)
            assertEquals(expected, get.bodyAsText())

            val read = client.put("/api/v1/notifications/missing/read")
            assertEquals(HttpStatusCode.NotFound, read.status)
            assertEquals(expected, read.bodyAsText())

            val delete = client.delete("/api/v1/notifications/missing")
            assertEquals(HttpStatusCode.NotFound, delete.status)
            assertEquals(expected, delete.bodyAsText())
        }
    }

    @Test
    fun `error constants carry the client-facing messages`() {
        assertEquals("Notification ID is required", NOTIFICATION_ID_REQUIRED)
        assertEquals("Notification not found", NOTIFICATION_NOT_FOUND)
    }
}
