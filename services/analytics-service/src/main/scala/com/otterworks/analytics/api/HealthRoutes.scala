package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.service.AnalyticsService
import io.prometheus.client.{CollectorRegistry, Counter, Gauge, Histogram}
import io.prometheus.client.exporter.common.TextFormat
import spray.json.*

import java.io.StringWriter
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
            complete(HttpEntity(
              ContentTypes.`application/json`,
              """{"status":"healthy","service":"analytics-service","eventsProcessed":0}"""
            ))
        }
      }
    },
    path("metrics") {
      get {
        val writer = new StringWriter()
        TextFormat.write004(writer, CollectorRegistry.defaultRegistry.metricFamilySamples())
        val metricsOutput = writer.toString
        complete(HttpEntity(ContentTypes.`text/plain(UTF-8)`, metricsOutput))
      }
    },
  )

object HealthRoutes:
  /** Prometheus metrics counters shared across the service. */
  val eventsReceivedTotal: Counter = Counter.build()
    .name("analytics_events_received_total")
    .help("Total number of analytics events received")
    .labelNames("event_type")
    .register()

  val requestDuration: Histogram = Histogram.build()
    .name("analytics_request_duration_seconds")
    .help("HTTP request duration in seconds")
    .labelNames("method", "path", "status")
    .register()

  val activeConnections: Gauge = Gauge.build()
    .name("analytics_active_connections")
    .help("Number of active HTTP connections")
    .register()
