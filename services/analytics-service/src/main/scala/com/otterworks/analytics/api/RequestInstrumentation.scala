package com.otterworks.analytics.api

import akka.http.scaladsl.model.headers.RawHeader
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import akka.http.scaladsl.settings.RoutingSettings
import net.logstash.logback.argument.StructuredArguments.kv
import org.slf4j.LoggerFactory

import java.util.UUID
import scala.util.matching.Regex

/**
 * Per-request observability for the HTTP layer:
 *   - `analytics_service_requests_total{method,endpoint,status}` and
 *     `analytics_service_request_duration_seconds{method,endpoint}` (see [[Metrics]])
 *   - one structured `http_request_completed` log line per request carrying
 *     `request_id`, `method`, `path`, `endpoint`, `status`, `duration_ms`
 *   - `X-Request-ID` propagation (reused from the gateway if present, else generated)
 *
 * `/health` and `/metrics` are excluded from metrics and request logs so probes and
 * scrapes do not drown out traffic, mirroring search-service.
 *
 * The `endpoint` label is the route template (e.g. `/api/v1/analytics/users/{id}/activity`)
 * rather than the raw path, to keep label cardinality bounded.
 */
object RequestInstrumentation:

  val RequestIdHeader = "X-Request-ID"

  private val logger = LoggerFactory.getLogger("com.otterworks.analytics.http")

  private val unmonitoredEndpoints = Set("/health", "/metrics")

  private val staticEndpoints: Set[String] = Set(
    "/health",
    "/metrics",
    "/api/v1/analytics/events",
    "/api/v1/analytics/dashboard",
    "/api/v1/analytics/top-content",
    "/api/v1/analytics/active-users",
    "/api/v1/analytics/storage",
    "/api/v1/analytics/export",
    "/api/v1/analytics/margins",
    "/api/v1/analytics/margins/series",
    "/api/v1/analytics/margins/export",
    "/api/v1/analytics/market/series",
    "/api/v1/analytics/market/prices",
    "/api/v1/analytics/market/status",
    "/api/v1/analytics/market/observations",
  )

  private val templatedEndpoints: Seq[(Regex, String)] = Seq(
    "/api/v1/analytics/users/{id}/activity",
    "/api/v1/analytics/documents/{id}/stats",
  ).map(template => (Regex.quote(template).replace("{id}", "\\E[^/]+\\Q").r, template))

  /** Map a request path onto its route template, or `unmatched` for unknown paths. */
  def endpointLabel(path: String): String =
    val normalized = if path.length > 1 && path.endsWith("/") then path.dropRight(1) else path
    if staticEndpoints.contains(normalized) then normalized
    else
      templatedEndpoints
        .collectFirst { case (pattern, template) if pattern.matches(normalized) => template }
        .getOrElse("unmatched")

  /** Wrap `inner` (sealed, so 404/500 responses are observed too) with metrics + request logging. */
  def instrumented(inner: Route): Route =
    extractSettings { settings =>
      given RoutingSettings = settings
      val sealedInner = Route.seal(inner)
      extractRequest { request =>
        val startNanos = System.nanoTime()
        val requestId = request.headers
          .collectFirst { case h if h.is("x-request-id") => h.value }
          .getOrElse(UUID.randomUUID().toString)
        val method = request.method.value
        val path = request.uri.path.toString
        val endpoint = endpointLabel(path)
        val monitored = !unmonitoredEndpoints.contains(endpoint)
        if monitored then Metrics.requestsInFlight.inc()

        mapResponse { response =>
          val elapsedNanos = System.nanoTime() - startNanos
          val status = response.status.intValue
          if monitored then
            Metrics.requestsInFlight.dec()
            Metrics.requestsTotal.labels(method, endpoint, status.toString).inc()
            Metrics.requestDuration.labels(method, endpoint).observe(elapsedNanos / 1e9)
            logger.info(
              "http_request_completed",
              kv("request_id", requestId),
              kv("method", method),
              kv("path", path),
              kv("endpoint", endpoint),
              kv("status", status),
              kv("duration_ms", elapsedNanos / 1e6),
            )
          response.addHeader(RawHeader(RequestIdHeader, requestId))
        }(sealedInner)
      }
    }
