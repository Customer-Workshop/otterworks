package com.otterworks.analytics.api

import akka.http.scaladsl.model.{ContentTypes, HttpEntity, HttpResponse, StatusCode}
import akka.http.scaladsl.server.Directives.mapResponse
import akka.http.scaladsl.server.Route
import spray.json.*

object ApiErrors:

  def standardize(route: Route): Route =
    mapResponse(standardizeResponse) {
      Route.seal(route)
    }

  private def standardizeResponse(response: HttpResponse): HttpResponse =
    if response.status.isFailure() then
      response.withEntity(
        HttpEntity(
          ContentTypes.`application/json`,
          errorJson(response.status),
        )
      )
    else response

  private def errorJson(status: StatusCode): String =
    JsObject(
      "error" -> JsObject(
        "code" -> JsString(codeFor(status.intValue)),
        "message" -> JsString(status.reason),
        "status" -> JsNumber(status.intValue),
      )
    ).compactPrint

  private def codeFor(status: Int): String =
    status match
      case 400 => "BAD_REQUEST"
      case 401 => "UNAUTHORIZED"
      case 403 => "FORBIDDEN"
      case 404 => "NOT_FOUND"
      case 405 => "METHOD_NOT_ALLOWED"
      case 409 => "CONFLICT"
      case 413 => "PAYLOAD_TOO_LARGE"
      case 422 => "VALIDATION_ERROR"
      case 429 => "RATE_LIMIT_EXCEEDED"
      case 500 => "INTERNAL_ERROR"
      case 502 => "BAD_GATEWAY"
      case 503 => "SERVICE_UNAVAILABLE"
      case _ => "HTTP_ERROR"
