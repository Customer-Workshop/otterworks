package com.otterworks.analytics.api

import org.apache.pekko.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import org.apache.pekko.http.scaladsl.server.Directives.*
import org.apache.pekko.http.scaladsl.server.Route
import com.otterworks.analytics.service.AnalyticsService
import io.prometheus.metrics.core.metrics.{Counter, Gauge, Histogram}
import io.prometheus.metrics.expositionformats.PrometheusTextFormatWriter
import io.prometheus.metrics.model.registry.PrometheusRegistry
import spray.json.*

import java.io.ByteArrayOutputStream
import scala.concurrent.ExecutionContext
import scala.util.{Failure, Success}

/**
 * Health and metrics endpoints:
 *   GET /health  - Service health check
 *   GET /metrics - Prometheus metrics
 */
class HealthRoutes(analyticsService: AnalyticsService)(using ec: ExecutionContext):

  val routes: Route = concat(
    path("health") {
      get {
        onComplete(analyticsService.getEventCount) {
          case Success(count) =>
            complete(HttpEntity(
              ContentTypes.`application/json`,
              s"""{"status":"healthy","service":"analytics-service","eventsProcessed":$count}"""
            ))
          case Failure(_) =>
            complete(StatusCodes.ServiceUnavailable, HttpEntity(
              ContentTypes.`application/json`,
              """{"status":"degraded","service":"analytics-service","eventsProcessed":0}"""
            ))
        }
      }
    },
    path("metrics") {
      get {
        val outputStream = new ByteArrayOutputStream()
        val writer = new PrometheusTextFormatWriter(false)
        writer.write(outputStream, PrometheusRegistry.defaultRegistry.scrape())
        val metricsOutput = outputStream.toString("UTF-8")
        complete(HttpEntity(ContentTypes.`text/plain(UTF-8)`, metricsOutput))
      }
    },
  )

object HealthRoutes:
  /** Prometheus metrics counters shared across the service. */
  val eventsReceivedTotal: Counter = Counter.builder()
    .name("analytics_events_received_total")
    .help("Total number of analytics events received")
    .labelNames("event_type")
    .register()

  val requestDuration: Histogram = Histogram.builder()
    .name("analytics_request_duration_seconds")
    .help("HTTP request duration in seconds")
    .labelNames("method", "path", "status")
    .register()

  val activeConnections: Gauge = Gauge.builder()
    .name("analytics_active_connections")
    .help("Number of active HTTP connections")
    .register()
