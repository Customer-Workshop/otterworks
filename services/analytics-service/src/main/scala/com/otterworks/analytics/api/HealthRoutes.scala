package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.service.AnalyticsService
import io.prometheus.client.CollectorRegistry
import io.prometheus.client.exporter.common.TextFormat
import spray.json.*

import java.io.StringWriter
import scala.concurrent.ExecutionContext
import scala.util.{Failure, Success}

/**
 * Health and metrics endpoints:
 *   GET /health  - Service health check
 *   GET /metrics - Prometheus metrics (text format 0.0.4, scraped by the Helm ServiceMonitor).
 *                  Metric definitions live in [[Metrics]].
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
        val writer = new StringWriter()
        TextFormat.write004(writer, CollectorRegistry.defaultRegistry.metricFamilySamples())
        val metricsOutput = writer.toString
        complete(HttpEntity(ContentTypes.`text/plain(UTF-8)`, metricsOutput))
      }
    },
  )
