package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import spray.json.*

object HealthRoutes:
  val routes: Route = concat(
    path("health") {
      get {
        complete(HttpEntity(
          ContentTypes.`application/json`,
          """{"status":"healthy","service":"analytics-service"}"""
        ))
      }
    },
    path("metrics") {
      get {
        complete(HttpEntity(
          ContentTypes.`text/plain(UTF-8)`,
          "# HELP analytics_service_up Analytics Service is running\n# TYPE analytics_service_up gauge\nanalytics_service_up 1\n"
        ))
      }
    },
  )
