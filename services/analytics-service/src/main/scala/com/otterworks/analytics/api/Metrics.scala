package com.otterworks.analytics.api

import io.prometheus.client.{Counter, Gauge, Histogram}
import io.prometheus.client.hotspot.DefaultExports

/**
 * Prometheus metrics for the analytics service, registered on the default
 * registry that `GET /metrics` renders (scraped by the Helm ServiceMonitor).
 *
 * Naming follows the platform convention used by search-service
 * (`<service>_<subject>_<unit>`), so the same dashboards/alerts apply:
 *   search_service_requests_total            <-> analytics_service_requests_total
 *   search_service_request_duration_seconds  <-> analytics_service_request_duration_seconds
 */
object Metrics:

  /** Total HTTP requests, by method, route template and response status. */
  val requestsTotal: Counter = Counter.build()
    .name("analytics_service_requests_total")
    .help("Total number of requests to the analytics service")
    .labelNames("method", "endpoint", "status")
    .register()

  /** HTTP request latency, by method and route template. */
  val requestDuration: Histogram = Histogram.build()
    .name("analytics_service_request_duration_seconds")
    .help("Request latency in seconds")
    .labelNames("method", "endpoint")
    .register()

  /** Requests currently being handled. */
  val requestsInFlight: Gauge = Gauge.build()
    .name("analytics_service_requests_in_flight")
    .help("Number of HTTP requests currently being handled")
    .register()

  /** Analytics events accepted for storage, by ingestion source and event type. */
  val eventsReceivedTotal: Counter = Counter.build()
    .name("analytics_service_events_received_total")
    .help("Total number of analytics events received")
    .labelNames("source", "event_type")
    .register()

  /** SQS messages seen by the event processor, by outcome. */
  val sqsMessagesTotal: Counter = Counter.build()
    .name("analytics_service_sqs_messages_total")
    .help("Total number of SQS messages consumed by the event processor")
    .labelNames("outcome")
    .register()

  /** Register the JVM/process collectors (`jvm_*`, `process_*`). Idempotent. */
  def registerJvmCollectors(): Unit = DefaultExports.initialize()

  /** Ingestion sources for `eventsReceivedTotal`. */
  object Source:
    val Api = "api"
    val Sqs = "sqs"

  /** Outcomes for `sqsMessagesTotal`. */
  object SqsOutcome:
    val Processed = "processed"
    val DecodeFailed = "decode_failed"
    val StoreFailed = "store_failed"
    val DeleteFailed = "delete_failed"
    val ReceiveFailed = "receive_failed"
