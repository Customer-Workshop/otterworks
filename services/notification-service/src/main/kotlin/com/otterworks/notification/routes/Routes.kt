package com.otterworks.notification.routes

import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.serialization.Serializable

@Serializable
data class HealthResponse(val status: String, val service: String)

@Serializable
data class NotificationResponse(
    val id: String,
    val userId: String,
    val type: String,
    val title: String,
    val message: String,
    val read: Boolean,
    val createdAt: String,
)

fun Application.configureRouting() {
    routing {
        get("/health") {
            call.respond(HealthResponse(status = "healthy", service = "notification-service"))
        }

        get("/metrics") {
            call.respondText(
                "# HELP notification_service_up Notification Service is running\n" +
                "# TYPE notification_service_up gauge\nnotification_service_up 1\n",
                contentType = ContentType.Text.Plain
            )
        }

        route("/api/v1/notifications") {
            get {
                // TODO: List notifications for authenticated user
                call.respond(mapOf("notifications" to emptyList<NotificationResponse>(), "total" to 0))
            }

            get("/{id}") {
                val id = call.parameters["id"] ?: return@get call.respond(HttpStatusCode.BadRequest)
                // TODO: Get notification by ID
                call.respond(HttpStatusCode.NotFound)
            }

            put("/{id}/read") {
                val id = call.parameters["id"] ?: return@put call.respond(HttpStatusCode.BadRequest)
                // TODO: Mark notification as read
                call.respond(HttpStatusCode.NoContent)
            }

            put("/read-all") {
                // TODO: Mark all notifications as read
                call.respond(HttpStatusCode.NoContent)
            }

            delete("/{id}") {
                val id = call.parameters["id"] ?: return@delete call.respond(HttpStatusCode.BadRequest)
                // TODO: Delete notification
                call.respond(HttpStatusCode.NoContent)
            }
        }
    }
}
