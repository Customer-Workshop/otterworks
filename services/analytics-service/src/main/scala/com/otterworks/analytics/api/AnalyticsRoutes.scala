package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import spray.json.*
import spray.json.DefaultJsonProtocol.*

object AnalyticsRoutes:
  private def jsonResponse(fields: (String, JsValue)*): HttpEntity.Strict =
    HttpEntity(ContentTypes.`application/json`, JsObject(fields*).compactPrint)

  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    concat(
      // Track an event
      path("events") {
        post {
          entity(as[String]) { body =>
            // TODO: Parse event and publish to SQS for async processing
            complete(StatusCodes.Accepted, jsonResponse("status" -> JsString("accepted")))
          }
        }
      },
      // Get usage statistics
      path("usage") {
        get {
          parameters("period".optional, "user_id".optional) { (period, userId) =>
            // TODO: Query aggregated analytics from S3 data lake
            complete(jsonResponse(
              "period" -> JsString(period.getOrElse("daily")),
              "metrics" -> JsObject(
                "documents_created" -> JsNumber(0),
                "files_uploaded" -> JsNumber(0),
                "active_users" -> JsNumber(0)
              )
            ))
          }
        }
      },
      // Get top documents
      path("top-documents") {
        get {
          parameters("limit".as[Int].withDefault(10)) { limit =>
            complete(jsonResponse(
              "documents" -> JsArray(),
              "limit" -> JsNumber(limit)
            ))
          }
        }
      },
      // Get active users
      path("active-users") {
        get {
          parameters("period".optional) { period =>
            complete(jsonResponse(
              "period" -> JsString(period.getOrElse("daily")),
              "users" -> JsArray(),
              "count" -> JsNumber(0)
            ))
          }
        }
      },
    )
  }
