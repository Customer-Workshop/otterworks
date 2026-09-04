package com.otterworks.notification.security

import com.otterworks.notification.model.Notification
import com.otterworks.notification.routes.ErrorResponse
import com.otterworks.notification.service.NotificationService
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.ApplicationCall
import io.ktor.server.application.call
import io.ktor.server.request.header
import io.ktor.server.response.respond
import io.ktor.server.websocket.DefaultWebSocketServerSession
import io.ktor.util.pipeline.PipelineContext
import io.ktor.websocket.CloseReason
import io.ktor.websocket.close

const val USER_ID_HEADER = "X-User-ID"

/** Caller identity injected by the api-gateway after it validates the JWT. */
fun ApplicationCall.callerId(): String? = request.header(USER_ID_HEADER)?.takeUnless { it.isBlank() }

/**
 * The authenticated caller, or null once a 401 has been responded. Identity is only ever
 * taken from the gateway header; request-supplied parameters are not trusted.
 */
suspend fun PipelineContext<Unit, ApplicationCall>.requireCaller(): String? {
    val caller = call.callerId()
    if (caller == null) {
        call.respond(
            HttpStatusCode.Unauthorized,
            ErrorResponse("Authentication required ($USER_ID_HEADER)"),
        )
    }
    return caller
}

/**
 * Requires [subjectUserId] to be the caller itself. Notifications and preferences have a
 * single owner and this service models no sharing, membership or admin role, so acting on
 * another user's data is never allowed.
 */
suspend fun PipelineContext<Unit, ApplicationCall>.requireSelf(
    caller: String,
    subjectUserId: String?,
): Boolean {
    if (subjectUserId.isNullOrBlank() || subjectUserId == caller) {
        return true
    }
    call.respond(HttpStatusCode.Forbidden, ErrorResponse("Forbidden"))
    return false
}

/**
 * Loads the notification named by the `{id}` path parameter and runs [block] only when the
 * authenticated caller owns it.
 */
suspend fun PipelineContext<Unit, ApplicationCall>.withOwnedNotification(
    service: NotificationService,
    block: suspend (Notification) -> Unit,
) {
    val caller = requireCaller() ?: return

    val id = call.parameters["id"]
    if (id.isNullOrBlank()) {
        call.respond(HttpStatusCode.BadRequest, ErrorResponse("Notification ID is required"))
        return
    }

    val notification = service.getNotificationById(id)
    if (notification == null) {
        call.respond(HttpStatusCode.NotFound, ErrorResponse("Notification not found"))
        return
    }
    if (notification.userId != caller) {
        call.respond(HttpStatusCode.Forbidden, ErrorResponse("Forbidden"))
        return
    }

    block(notification)
}

/**
 * WebSocket counterpart: the stream may only carry the authenticated caller's own
 * notifications. Closes the socket and returns null when that does not hold.
 */
suspend fun DefaultWebSocketServerSession.requireWebSocketCaller(subjectUserId: String?): String? {
    val caller = call.callerId()
    if (caller == null) {
        close(CloseReason(CloseReason.Codes.VIOLATED_POLICY, "Authentication required"))
        return null
    }
    if (subjectUserId != caller) {
        close(
            CloseReason(
                CloseReason.Codes.VIOLATED_POLICY,
                "Cannot subscribe to another user's notifications",
            ),
        )
        return null
    }
    return caller
}
