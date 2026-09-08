package com.otterworks.analytics.api

import akka.http.scaladsl.marshallers.sprayjson.SprayJsonSupport.*
import akka.http.scaladsl.model.StatusCodes
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.model.AnalyticsEventJsonProtocol.{*, given}
import com.otterworks.analytics.service.AnalyticsService
import net.logstash.logback.argument.StructuredArguments.kv
import org.slf4j.LoggerFactory

/** Routes for event ingestion: POST /api/v1/analytics/events */
class EventRoutes(analyticsService: AnalyticsService):

  private val logger = LoggerFactory.getLogger(getClass)

  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    path("events") {
      post {
        entity(as[TrackEventRequest]) { request =>
          onSuccess(
            analyticsService.trackEvent(
              request.eventType,
              request.userId,
              request.resourceId,
              request.resourceType,
              request.metadata.getOrElse(Map.empty)
            )
          ) { event =>
            Metrics.eventsReceivedTotal.labels(Metrics.Source.Api, event.eventType).inc()
            logger.info(
              "event_accepted",
              kv("source", Metrics.Source.Api),
              kv("event_id", event.eventId),
              kv("event_type", event.eventType),
              kv("user_id", event.userId),
              kv("resource_id", event.resourceId),
              kv("resource_type", event.resourceType),
            )
            complete(StatusCodes.Accepted, AcceptedResponse("accepted", event.eventId))
          }
        }
      }
    }
  }
