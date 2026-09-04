package com.otterworks.notification.routes

import com.otterworks.notification.configurePlugins
import com.otterworks.notification.config.AppConfig
import com.otterworks.notification.model.DeliveryChannel
import com.otterworks.notification.model.Notification
import com.otterworks.notification.model.NotificationPreference
import com.otterworks.notification.security.USER_ID_HEADER
import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.ktor.client.plugins.websocket.WebSockets as ClientWebSockets
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.ApplicationTestBuilder
import io.ktor.server.testing.testApplication
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import io.ktor.websocket.readText
import io.micrometer.prometheus.PrometheusConfig
import io.micrometer.prometheus.PrometheusMeterRegistry
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.withTimeout
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.koin.ktor.plugin.Koin
import io.ktor.server.application.install
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

private const val OWNER = "user-owner"
private const val ATTACKER = "user-attacker"

private val ownedNotification = Notification(
    id = "n-1",
    userId = OWNER,
    type = "file_shared",
    title = "File Shared With You",
    message = "A file was shared",
    createdAt = "2024-01-01T00:00:00Z",
)

class RoutesAuthorizationTest {

    private val notificationService = mockk<NotificationService>(relaxed = true)
    private val webSocketManager = WebSocketManager()

    @BeforeTest
    @AfterTest
    fun resetKoin() {
        stopKoin()
    }

    private fun ApplicationTestBuilder.configureTestApp() {
        application {
            configurePlugins(AppConfig.load())
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
    fun `owner can read their own notification`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification

        val response = client.get("/api/v1/notifications/n-1") { header(USER_ID_HEADER, OWNER) }
        assertEquals(HttpStatusCode.OK, response.status)
    }

    @Test
    fun `another user cannot read someone elses notification`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification

        val response = client.get("/api/v1/notifications/n-1") { header(USER_ID_HEADER, ATTACKER) }
        assertEquals(HttpStatusCode.Forbidden, response.status)
    }

    @Test
    fun `reading a notification without an identity header is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.get("/api/v1/notifications/n-1")
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.getNotificationById(any()) }
    }

    @Test
    fun `owner can mark their own notification read`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification
        coEvery { notificationService.markAsRead("n-1") } returns true

        val response = client.put("/api/v1/notifications/n-1/read") { header(USER_ID_HEADER, OWNER) }
        assertEquals(HttpStatusCode.NoContent, response.status)
    }

    @Test
    fun `another user cannot mark someone elses notification read`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification

        val response = client.put("/api/v1/notifications/n-1/read") { header(USER_ID_HEADER, ATTACKER) }
        assertEquals(HttpStatusCode.Forbidden, response.status)
        coVerify(exactly = 0) { notificationService.markAsRead(any()) }
    }

    @Test
    fun `owner can delete their own notification`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification
        coEvery { notificationService.deleteNotification("n-1") } returns true

        val response = client.delete("/api/v1/notifications/n-1") { header(USER_ID_HEADER, OWNER) }
        assertEquals(HttpStatusCode.NoContent, response.status)
    }

    @Test
    fun `another user cannot delete someone elses notification`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("n-1") } returns ownedNotification

        val response = client.delete("/api/v1/notifications/n-1") { header(USER_ID_HEADER, ATTACKER) }
        assertEquals(HttpStatusCode.Forbidden, response.status)
        coVerify(exactly = 0) { notificationService.deleteNotification(any()) }
    }

    @Test
    fun `deleting without an identity header is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.delete("/api/v1/notifications/n-1")
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.deleteNotification(any()) }
    }

    @Test
    fun `an unknown notification is still a 404 for an authenticated caller`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotificationById("missing") } returns null

        val response = client.get("/api/v1/notifications/missing") { header(USER_ID_HEADER, OWNER) }
        assertEquals(HttpStatusCode.NotFound, response.status)
    }

    @Test
    fun `list is scoped to the header caller and ignores the user_id query parameter`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getNotifications(any(), any(), any()) } returns Pair(emptyList(), 0)

        val response = client.get("/api/v1/notifications?user_id=$OWNER") { header(USER_ID_HEADER, ATTACKER) }
        assertEquals(HttpStatusCode.OK, response.status)
        coVerify { notificationService.getNotifications(ATTACKER, any(), any()) }
        coVerify(exactly = 0) { notificationService.getNotifications(OWNER, any(), any()) }
    }

    @Test
    fun `listing with only a user_id query parameter is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.get("/api/v1/notifications?user_id=$OWNER")
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.getNotifications(any(), any(), any()) }
    }

    @Test
    fun `unread count with only a user_id query parameter is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.get("/api/v1/notifications/unread-count?user_id=$OWNER")
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.getUnreadCount(any()) }
    }

    @Test
    fun `read-all with only a user_id query parameter is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.put("/api/v1/notifications/read-all?user_id=$OWNER")
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.markAllAsRead(any()) }
    }

    @Test
    fun `preferences are read for the header caller only`() = testApplication {
        configureTestApp()
        coEvery { notificationService.getPreferences(ATTACKER) } returns NotificationPreference(userId = ATTACKER)

        val response = client.get("/api/v1/preferences?user_id=$OWNER") { header(USER_ID_HEADER, ATTACKER) }
        assertEquals(HttpStatusCode.OK, response.status)
        coVerify(exactly = 0) { notificationService.getPreferences(OWNER) }
    }

    @Test
    fun `owner can update their own preferences`() = testApplication {
        configureTestApp()

        val response = client.put("/api/v1/preferences") {
            header(USER_ID_HEADER, OWNER)
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"$OWNER","eventType":"file_shared","channels":["EMAIL"]}""")
        }
        assertEquals(HttpStatusCode.NoContent, response.status)
        coVerify { notificationService.updatePreferences(OWNER, "file_shared", listOf(DeliveryChannel.EMAIL)) }
    }

    @Test
    fun `another user cannot update someone elses preferences`() = testApplication {
        configureTestApp()

        val response = client.put("/api/v1/preferences") {
            header(USER_ID_HEADER, ATTACKER)
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"$OWNER","eventType":"file_shared","channels":[]}""")
        }
        assertEquals(HttpStatusCode.Forbidden, response.status)
        coVerify(exactly = 0) { notificationService.updatePreferences(any(), any(), any()) }
    }

    @Test
    fun `updating preferences without an identity header is unauthorized`() = testApplication {
        configureTestApp()

        val response = client.put("/api/v1/preferences") {
            contentType(ContentType.Application.Json)
            setBody("""{"userId":"$OWNER","eventType":"file_shared","channels":[]}""")
        }
        assertEquals(HttpStatusCode.Unauthorized, response.status)
        coVerify(exactly = 0) { notificationService.updatePreferences(any(), any(), any()) }
    }

    @Test
    fun `owner can open their own notification stream`() = testApplication {
        configureTestApp()
        val wsClient = createClient { install(ClientWebSockets) }

        val session = wsClient.webSocketSession("/ws/notifications/$OWNER") {
            header(USER_ID_HEADER, OWNER)
        }
        withTimeout(5_000) {
            session.send(Frame.Text("ping"))
            val reply = session.incoming.receive() as Frame.Text
            assertEquals("pong", reply.readText())
            assertEquals(true, webSocketManager.isUserConnected(OWNER))
            session.close()
        }
    }

    @Test
    fun `another user cannot subscribe to someone elses notification stream`() = testApplication {
        configureTestApp()
        val wsClient = createClient { install(ClientWebSockets) }

        val session = wsClient.webSocketSession("/ws/notifications/$OWNER") {
            header(USER_ID_HEADER, ATTACKER)
        }
        val reason = withTimeout(5_000) { session.closeReason.await() }
        assertNotNull(reason)
        assertEquals(CloseReason.Codes.VIOLATED_POLICY.code, reason.code)
        assertEquals(false, webSocketManager.isUserConnected(OWNER))
    }

    @Test
    fun `subscribing without an identity header is rejected`() = testApplication {
        configureTestApp()
        val wsClient = createClient { install(ClientWebSockets) }

        val session = wsClient.webSocketSession("/ws/notifications/$OWNER")
        val reason = withTimeout(5_000) { session.closeReason.await() }
        assertNotNull(reason)
        assertEquals(CloseReason.Codes.VIOLATED_POLICY.code, reason.code)
        assertEquals(false, webSocketManager.isUserConnected(OWNER))
    }
}
