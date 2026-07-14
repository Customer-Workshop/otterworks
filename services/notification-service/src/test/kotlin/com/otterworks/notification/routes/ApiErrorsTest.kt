package com.otterworks.notification.routes

import com.otterworks.notification.configurePlugins
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals

class ApiErrorsTest {

    @Test
    fun `serializes standard error response`() {
        val response = ErrorResponse(
            ErrorDetail(
                code = "NOT_FOUND",
                message = "Notification not found",
                status = 404,
            )
        )

        assertEquals(
            """{"error":{"code":"NOT_FOUND","message":"Notification not found","status":404}}""",
            Json.encodeToString(response),
        )
    }

    @Test
    fun `unknown routes use the standard error response`() = testApplication {
        application {
            configurePlugins()
        }

        val response = client.get("/missing")

        assertEquals(HttpStatusCode.NotFound, response.status)
        assertEquals(
            """{"error":{"code":"NOT_FOUND","message":"Route not found","status":404}}""",
            response.bodyAsText(),
        )
    }
}
