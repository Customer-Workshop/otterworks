package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route

object AnalyticsRoutes:
  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    concat(
      // Track an event
      path("events") {
        post {
          entity(as[String]) { body =>
            // TODO: Parse event and publish to SQS for async processing
            complete(StatusCodes.Accepted, HttpEntity(
              ContentTypes.`application/json`,
              """{"status":"accepted"}"""
            ))
          }
        }
      },
      // Get usage statistics
      path("usage") {
        get {
          parameters("period".optional, "user_id".optional) { (period, userId) =>
            // TODO: Query aggregated analytics from S3 data lake
            complete(HttpEntity(
              ContentTypes.`application/json`,
              s"""{"period":"${period.getOrElse("daily")}","metrics":{"documents_created":0,"files_uploaded":0,"active_users":0}}"""
            ))
          }
        }
      },
      // Get top documents
      path("top-documents") {
        get {
          parameters("limit".as[Int].withDefault(10)) { limit =>
            complete(HttpEntity(
              ContentTypes.`application/json`,
              s"""{"documents":[],"limit":$limit}"""
            ))
          }
        }
      },
      // Get active users
      path("active-users") {
        get {
          parameters("period".optional) { period =>
            complete(HttpEntity(
              ContentTypes.`application/json`,
              s"""{"period":"${period.getOrElse("daily")}","users":[],"count":0}"""
            ))
          }
        }
      },
    )
  }
