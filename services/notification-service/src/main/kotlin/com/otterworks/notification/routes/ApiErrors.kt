package com.otterworks.notification.routes

import io.ktor.http.HttpStatusCode
import io.ktor.server.application.ApplicationCall
import io.ktor.server.response.respond
import kotlinx.serialization.Serializable

@Serializable
data class ErrorDetail(
    val code: String,
    val message: String,
    val status: Int,
)

@Serializable
data class ErrorResponse(val error: ErrorDetail)

suspend fun ApplicationCall.respondError(
    status: HttpStatusCode,
    code: String,
    message: String,
) {
    respond(
        status,
        ErrorResponse(
            ErrorDetail(
                code = code,
                message = message,
                status = status.value,
            )
        ),
    )
}
