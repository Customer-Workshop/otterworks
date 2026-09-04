package com.otterworks.analytics.api

import akka.http.scaladsl.marshallers.sprayjson.SprayJsonSupport.*
import akka.http.scaladsl.model.StatusCodes
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.api.CallerDirectives.callerSubject
import com.otterworks.analytics.model.AnalyticsEventJsonProtocol.{*, given}
import com.otterworks.analytics.service.AnalyticsService
import org.slf4j.LoggerFactory

/** Routes for event ingestion: POST /api/v1/analytics/events */
class EventRoutes(analyticsService: AnalyticsService):

  private val logger = LoggerFactory.getLogger(getClass)

  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    path("events") {
      post {
        entity(as[TrackEventRequest]) { request =>
          // The event is attributed to the authenticated caller; a body userId
          // may only restate it.
          callerSubject(Option(request.userId)) { caller =>
            onSuccess(
              analyticsService.trackEvent(
                request.eventType,
                caller,
                request.resourceId,
                request.resourceType,
                request.metadata.getOrElse(Map.empty)
              )
            ) { event =>
              logger.info("Event tracked: {}", event.eventId)
              complete(StatusCodes.Accepted, AcceptedResponse("accepted", event.eventId))
            }
          }
        }
      }
    }
  }
