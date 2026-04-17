package com.otterworks.notification

import com.otterworks.notification.config.AppConfig
import com.otterworks.notification.consumer.SqsConsumer
import com.otterworks.notification.routes.configureRouting
import io.ktor.serialization.kotlinx.json.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.plugins.cors.routing.*
import io.ktor.server.plugins.statuspages.*
import io.ktor.http.*
import io.ktor.server.response.*
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

fun main() {
    val config = AppConfig.load()

    embeddedServer(Netty, port = config.port, host = "0.0.0.0") {
        configurePlugins()
        configureRouting()

        // Start SQS consumer in a coroutine
        launch {
            val consumer = SqsConsumer(config)
            consumer.startPolling()
        }

        logger.info { "Notification Service started on port ${config.port}" }
    }.start(wait = true)
}

fun Application.configurePlugins() {
    install(ContentNegotiation) {
        json(Json {
            prettyPrint = false
            isLenient = true
            ignoreUnknownKeys = true
        })
    }

    install(CORS) {
        allowHost("localhost:3000")
        allowHost("localhost:4200")
        allowHeader(HttpHeaders.ContentType)
        allowHeader(HttpHeaders.Authorization)
        allowMethod(HttpMethod.Put)
        allowMethod(HttpMethod.Delete)
        allowMethod(HttpMethod.Patch)
    }

    install(StatusPages) {
        exception<Throwable> { call, cause ->
            logger.error(cause) { "Unhandled exception" }
            call.respondText(
                text = """{"error":"${cause.message}"}""",
                contentType = ContentType.Application.Json,
                status = HttpStatusCode.InternalServerError
            )
        }
    }
}
