package com.otterworks.analytics

import akka.actor.typed.ActorSystem
import akka.actor.typed.scaladsl.Behaviors
import akka.http.scaladsl.Http
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.api.{AnalyticsRoutes, EventRoutes, HealthRoutes}
import com.otterworks.analytics.config.AppConfig
import com.otterworks.analytics.repository.MetricsRepository
import com.otterworks.analytics.service.{AnalyticsService, EventProcessor}

import scala.concurrent.{Await, ExecutionContextExecutor}
import scala.concurrent.duration.Duration
import scala.util.{Failure, Success}

object Main:
  def main(args: Array[String]): Unit =
    given system: ActorSystem[Nothing] = ActorSystem(Behaviors.empty, "analytics-service")
    given ec: ExecutionContextExecutor = system.executionContext

    val config = AppConfig.load()

    // Wire up dependencies
    val repository = MetricsRepository(config.postgres)
    val analyticsService = AnalyticsService(repository)
    val eventProcessor = EventProcessor(config, analyticsService)

    // Build routes
    val healthRoutes = HealthRoutes(analyticsService)
    val analyticsRoutes = AnalyticsRoutes(analyticsService)
    val eventRoutes = EventRoutes(analyticsService)

    val routes: Route = concat(
      healthRoutes.routes,
      eventRoutes.routes,
      analyticsRoutes.routes,
    )

    val host = config.server.host
    val port = config.server.port

    val binding = Http().newServerAt(host, port).bind(routes)
    binding.onComplete {
      case Success(b) =>
        system.log.info(s"Analytics Service started at http://${b.localAddress.getHostString}:${b.localAddress.getPort}")
        // Start SQS consumer in background (non-fatal if SQS unavailable)
        try eventProcessor.start()
        catch case ex: Exception =>
          system.log.warn(s"SQS event processor could not start: ${ex.getMessage}. Running without SQS ingestion.")
      case Failure(e) =>
        system.log.error(s"Failed to start Analytics Service: ${e.getMessage}")
        system.terminate()
    }

    Await.result(system.whenTerminated, Duration.Inf)
