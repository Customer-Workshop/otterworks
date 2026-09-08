package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, MediaTypes, StatusCodes}
import akka.http.scaladsl.model.headers.RawHeader
import akka.http.scaladsl.server.Directives.concat
import akka.http.scaladsl.server.Route
import akka.http.scaladsl.testkit.ScalatestRouteTest
import ch.qos.logback.classic.{Logger, LoggerContext}
import ch.qos.logback.classic.spi.ILoggingEvent
import ch.qos.logback.core.ConsoleAppender
import ch.qos.logback.core.read.ListAppender
import com.otterworks.analytics.config.PostgresConfig
import com.otterworks.analytics.model.*
import com.otterworks.analytics.model.AnalyticsEventJsonProtocol.{*, given}
import com.otterworks.analytics.repository.MetricsRepository
import com.otterworks.analytics.service.AnalyticsService
import io.prometheus.client.CollectorRegistry
import org.scalatest.BeforeAndAfterEach
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import org.slf4j.LoggerFactory
import spray.json.*

import java.nio.charset.StandardCharsets.UTF_8
import scala.jdk.CollectionConverters.*

/**
 * Verifies the observability contract of the analytics service:
 *   - GET /metrics serves the `analytics_service_*` families in Prometheus text format
 *     (what the Helm ServiceMonitor scrapes)
 *   - every instrumented request is counted/timed under a bounded route template
 *   - probes/scrapes (/health, /metrics) are excluded from request metrics
 *   - one structured JSON request log line is emitted per request
 */
class ObservabilitySpec extends AnyFlatSpec with Matchers with ScalatestRouteTest with BeforeAndAfterEach:

  private val testConfig: PostgresConfig = PostgresConfig(
    url = "jdbc:postgresql://localhost:5432/test",
    user = "test",
    password = "test",
    maxPoolSize = 2
  )

  private val routes: Route =
    val service = AnalyticsService(MetricsRepository(testConfig))
    RequestInstrumentation.instrumented(
      concat(
        HealthRoutes(service).routes,
        EventRoutes(service).routes,
        AnalyticsRoutes(service).routes,
      )
    )

  private val registry = CollectorRegistry.defaultRegistry

  private def requestsTotal(method: String, endpoint: String, status: Int): Double =
    Option(registry.getSampleValue(
      "analytics_service_requests_total",
      Array("method", "endpoint", "status"),
      Array(method, endpoint, status.toString))).map(_.doubleValue).getOrElse(0.0)

  private def durationCount(method: String, endpoint: String): Double =
    Option(registry.getSampleValue(
      "analytics_service_request_duration_seconds_count",
      Array("method", "endpoint"),
      Array(method, endpoint))).map(_.doubleValue).getOrElse(0.0)

  private def inFlight: Double =
    Option(registry.getSampleValue("analytics_service_requests_in_flight")).map(_.doubleValue).getOrElse(0.0)

  // Capture the structured request log and render it through the configured
  // LogstashEncoder so the assertions cover the real logback.xml output.
  // Suites run in parallel, so wait for SLF4J to finish binding logback before
  // asking for logback-specific types (the factory is a substitute meanwhile).
  private lazy val loggerContext: LoggerContext =
    var factory = LoggerFactory.getILoggerFactory
    var attempts = 0
    while !factory.isInstanceOf[LoggerContext] && attempts < 100 do
      Thread.sleep(20)
      attempts += 1
      factory = LoggerFactory.getILoggerFactory
    factory match
      case ctx: LoggerContext => ctx
      case other => fail(s"logback did not initialise; SLF4J factory is ${other.getClass.getName}")

  private lazy val httpLogger: Logger = loggerContext.getLogger("com.otterworks.analytics.http")
  private val captured = new ListAppender[ILoggingEvent]()

  private def encodeWithConfiguredEncoder(event: ILoggingEvent): JsObject =
    val root = loggerContext.getLogger(org.slf4j.Logger.ROOT_LOGGER_NAME)
    val appender = root.getAppender("STDOUT").asInstanceOf[ConsoleAppender[ILoggingEvent]]
    new String(appender.getEncoder.encode(event), UTF_8).parseJson.asJsObject

  override def beforeEach(): Unit =
    captured.list.clear()
    captured.setContext(loggerContext)
    captured.start()
    httpLogger.addAppender(captured)

  override def afterEach(): Unit =
    httpLogger.detachAppender(captured)
    captured.stop()

  // --- GET /metrics (ServiceMonitor contract) ---

  "GET /metrics" should "expose analytics_service_* metrics in Prometheus text format" in {
    Get("/api/v1/analytics/dashboard?period=7d") ~> routes ~> check {
      status shouldBe StatusCodes.OK
    }
    Get("/metrics") ~> routes ~> check {
      status shouldBe StatusCodes.OK
      contentType.mediaType shouldBe MediaTypes.`text/plain`
      val body = responseAs[String]
      body should include("# TYPE analytics_service_requests_total counter")
      body should include("# TYPE analytics_service_request_duration_seconds histogram")
      body should include("# TYPE analytics_service_requests_in_flight gauge")
      body should include("# TYPE analytics_service_events_received_total counter")
      body should include("# TYPE analytics_service_sqs_messages_total counter")
      body should include regex
        """analytics_service_requests_total\{method="GET",endpoint="/api/v1/analytics/dashboard",status="200",?\} \d"""
    }
  }

  it should "not count itself or /health in request metrics" in {
    val metricsBefore = requestsTotal("GET", "/metrics", 200)
    val healthBefore = requestsTotal("GET", "/health", 200)
    Get("/metrics") ~> routes ~> check { status shouldBe StatusCodes.OK }
    Get("/health") ~> routes ~> check { status shouldBe StatusCodes.OK }
    Get("/metrics") ~> routes ~> check {
      val body = responseAs[String]
      body should not include """endpoint="/metrics""""
      body should not include """endpoint="/health""""
    }
    requestsTotal("GET", "/metrics", 200) shouldBe metricsBefore
    requestsTotal("GET", "/health", 200) shouldBe healthBefore
    captured.list.asScala.map(_.getFormattedMessage) should not contain "http_request_completed"
  }

  // --- Request metrics ---

  "Request instrumentation" should "count and time requests under the route template, not the raw path" in {
    val endpoint = "/api/v1/analytics/users/{id}/activity"
    val countBefore = requestsTotal("GET", endpoint, 200)
    val durationBefore = durationCount("GET", endpoint)

    Get("/api/v1/analytics/users/user-42/activity") ~> routes ~> check {
      status shouldBe StatusCodes.OK
    }
    Get("/api/v1/analytics/users/user-43/activity") ~> routes ~> check {
      status shouldBe StatusCodes.OK
    }

    requestsTotal("GET", endpoint, 200) shouldBe countBefore + 2
    durationCount("GET", endpoint) shouldBe durationBefore + 2
    requestsTotal("GET", "/api/v1/analytics/users/user-42/activity", 200) shouldBe 0.0
    inFlight shouldBe 0.0
  }

  it should "record the response status, including sealed 404s under a bounded label" in {
    val eventsBefore = requestsTotal("POST", "/api/v1/analytics/events", 202)
    val unmatchedBefore = requestsTotal("GET", "unmatched", 404)

    val payload = TrackEventRequest("document.viewed", "user-1", "doc-1", "document", None).toJson.compactPrint
    Post("/api/v1/analytics/events", HttpEntity(ContentTypes.`application/json`, payload)) ~> routes ~> check {
      status shouldBe StatusCodes.Accepted
    }
    Get("/no/such/route") ~> routes ~> check {
      status shouldBe StatusCodes.NotFound
    }

    requestsTotal("POST", "/api/v1/analytics/events", 202) shouldBe eventsBefore + 1
    requestsTotal("GET", "unmatched", 404) shouldBe unmatchedBefore + 1
  }

  it should "count accepted events by source and type" in {
    val before = Option(registry.getSampleValue(
      "analytics_service_events_received_total",
      Array("source", "event_type"),
      Array("api", "document.shared"))).map(_.doubleValue).getOrElse(0.0)

    val payload = TrackEventRequest("document.shared", "user-1", "doc-1", "document", None).toJson.compactPrint
    Post("/api/v1/analytics/events", HttpEntity(ContentTypes.`application/json`, payload)) ~> routes ~> check {
      status shouldBe StatusCodes.Accepted
    }

    registry.getSampleValue(
      "analytics_service_events_received_total",
      Array("source", "event_type"),
      Array("api", "document.shared")).doubleValue shouldBe before + 1
  }

  // --- X-Request-ID ---

  it should "echo an incoming X-Request-ID and generate one when absent" in {
    Get("/api/v1/analytics/dashboard").withHeaders(RawHeader("X-Request-ID", "req-abc-123")) ~> routes ~> check {
      header("X-Request-ID").map(_.value) shouldBe Some("req-abc-123")
    }
    Get("/api/v1/analytics/dashboard") ~> routes ~> check {
      header("X-Request-ID").map(_.value).getOrElse("") should fullyMatch regex
        "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    }
  }

  it should "replace malformed or oversized X-Request-ID values with a generated one" in {
    val uuidPattern = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    Seq("a" * 129, "id with spaces", "id\"quoted", "{\"json\":1}", "").foreach { bad =>
      Get("/api/v1/analytics/dashboard").withHeaders(RawHeader("X-Request-ID", bad)) ~> routes ~> check {
        val echoed = header("X-Request-ID").map(_.value).getOrElse("")
        echoed should not be bad
        echoed should fullyMatch regex uuidPattern
      }
    }
  }

  // --- Structured request log ---

  "Request log" should "emit one JSON line per request with the standard fields" in {
    Get("/api/v1/analytics/documents/doc-7/stats")
      .withHeaders(RawHeader("X-Request-ID", "req-log-1")) ~> routes ~> check {
      status shouldBe StatusCodes.OK
    }

    val events = captured.list.asScala.filter(_.getFormattedMessage == "http_request_completed")
    events should have size 1
    val json = encodeWithConfiguredEncoder(events.head).fields

    json("service") shouldBe JsString("analytics-service")
    json("level") shouldBe JsString("INFO")
    json("message") shouldBe JsString("http_request_completed")
    json should contain key "timestamp"
    json("request_id") shouldBe JsString("req-log-1")
    json("method") shouldBe JsString("GET")
    json("path") shouldBe JsString("/api/v1/analytics/documents/doc-7/stats")
    json("endpoint") shouldBe JsString("/api/v1/analytics/documents/{id}/stats")
    json("status") shouldBe JsNumber(200)
    json("duration_ms").asInstanceOf[JsNumber].value should be >= BigDecimal(0)
    json.keySet should not contain "level_value"
    json.keySet should not contain "@version"
  }

  // --- Endpoint templating ---

  "endpointLabel" should "map known paths to bounded route templates" in {
    RequestInstrumentation.endpointLabel("/health") shouldBe "/health"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/events") shouldBe "/api/v1/analytics/events"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/dashboard/") shouldBe "/api/v1/analytics/dashboard"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/users/u-1/activity") shouldBe
      "/api/v1/analytics/users/{id}/activity"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/documents/d%202/stats") shouldBe
      "/api/v1/analytics/documents/{id}/stats"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/market/status") shouldBe "/api/v1/analytics/market/status"
    RequestInstrumentation.endpointLabel("/api/v1/analytics/users/u-1/activity/extra") shouldBe "unmatched"
    RequestInstrumentation.endpointLabel("/admin") shouldBe "unmatched"
  }
