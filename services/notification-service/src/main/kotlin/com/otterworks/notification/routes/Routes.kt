package com.otterworks.notification.routes

import com.otterworks.notification.model.NotificationPreferenceRequest
import com.otterworks.notification.model.PaginatedResponse
import com.otterworks.notification.model.UnreadCountResponse
import com.otterworks.notification.security.requireCaller
import com.otterworks.notification.security.requireSelf
import com.otterworks.notification.security.requireWebSocketCaller
import com.otterworks.notification.security.withOwnedNotification
import com.otterworks.notification.service.NotificationService
import com.otterworks.notification.websocket.WebSocketManager
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.Application
import io.ktor.server.application.call
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.response.respondText
import io.ktor.server.routing.delete
import io.ktor.server.routing.get
import io.ktor.server.routing.put
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.websocket.webSocket
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import io.micrometer.prometheus.PrometheusMeterRegistry
import kotlinx.serialization.Serializable
import org.koin.ktor.ext.inject

@Serializable
data class HealthResponse(val status: String, val service: String)

@Serializable
data class ErrorResponse(val error: String)

@Serializable
data class MarkAllReadResponse(val markedCount: Int)

fun Application.configureRouting(prometheusRegistry: PrometheusMeterRegistry) {
    val notificationService by inject<NotificationService>()
    val webSocketManager by inject<WebSocketManager>()

    routing {
        get("/health") {
            call.respond(HealthResponse(status = "healthy", service = "notification-service"))
        }

        get("/metrics") {
            call.respondText(
                prometheusRegistry.scrape(),
                contentType = io.ktor.http.ContentType.Text.Plain,
            )
        }

        route("/api/v1/notifications") {
            get {
                val userId = requireCaller() ?: return@get

                val page = call.request.queryParameters["page"]?.toIntOrNull() ?: 1
                val pageSize = call.request.queryParameters["page_size"]?.toIntOrNull() ?: 20

                val (notifications, total) = notificationService.getNotifications(userId, page, pageSize)

                call.respond(
                    PaginatedResponse(
                        data = notifications,
                        total = total,
                        page = page,
                        pageSize = pageSize,
                        hasMore = (page * pageSize) < total,
                    )
                )
            }

            get("/unread-count") {
                val userId = requireCaller() ?: return@get

                val count = notificationService.getUnreadCount(userId)
                call.respond(UnreadCountResponse(userId = userId, unreadCount = count))
            }

            get("/{id}") {
                withOwnedNotification(notificationService) { notification ->
                    call.respond(notification)
                }
            }

            put("/{id}/read") {
                withOwnedNotification(notificationService) { notification ->
                    val success = notificationService.markAsRead(notification.id)
                    if (success) {
                        call.respond(HttpStatusCode.NoContent)
                    } else {
                        call.respond(HttpStatusCode.NotFound, ErrorResponse("Notification not found"))
                    }
                }
            }

            put("/read-all") {
                val userId = requireCaller() ?: return@put

                val count = notificationService.markAllAsRead(userId)
                call.respond(MarkAllReadResponse(markedCount = count))
            }

            delete("/{id}") {
                withOwnedNotification(notificationService) { notification ->
                    val success = notificationService.deleteNotification(notification.id)
                    if (success) {
                        call.respond(HttpStatusCode.NoContent)
                    } else {
                        call.respond(HttpStatusCode.NotFound, ErrorResponse("Notification not found"))
                    }
                }
            }
        }

        route("/api/v1/preferences") {
            get {
                val userId = requireCaller() ?: return@get

                val preferences = notificationService.getPreferences(userId)
                call.respond(preferences)
            }

            put {
                val userId = requireCaller() ?: return@put

                val request = call.receive<NotificationPreferenceRequest>()
                if (!requireSelf(userId, request.userId)) return@put

                notificationService.updatePreferences(
                    userId = userId,
                    eventType = request.eventType,
                    channels = request.channels,
                )
                call.respond(HttpStatusCode.NoContent)
            }
        }

        webSocket("/ws/notifications/{userId}") {
            val userId = requireWebSocketCaller(call.parameters["userId"]) ?: return@webSocket

            webSocketManager.addConnection(userId, this)

            try {
                for (frame in incoming) {
                    when (frame) {
                        is Frame.Text -> {
                            val text = frame.readText()
                            // Handle ping/pong or client messages if needed
                            if (text == "ping") {
                                send(Frame.Text("pong"))
                            }
                        }
                        is Frame.Close -> break
                        else -> { /* ignore other frame types */ }
                    }
                }
            } finally {
                webSocketManager.removeConnection(userId, this)
            }
        }
    }
}
