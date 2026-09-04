package com.otterworks.analytics.api

import akka.http.scaladsl.marshallers.sprayjson.SprayJsonSupport.*
import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.api.CallerDirectives.{callerId, callerOwning, callerSubject}
import com.otterworks.analytics.model.DashboardJsonProtocol.{*, given}
import com.otterworks.analytics.service.AnalyticsService
import spray.json.*

import java.time.Instant

/**
 * Analytics query routes:
 *   GET /api/v1/analytics/dashboard
 *   GET /api/v1/analytics/users/{id}/activity
 *   GET /api/v1/analytics/documents/{id}/stats
 *   GET /api/v1/analytics/top-content
 *   GET /api/v1/analytics/active-users
 *   GET /api/v1/analytics/storage
 *   GET /api/v1/analytics/export
 *
 * User-scoped routes (user activity, document stats, storage, export) resolve
 * the caller from `X-User-ID` via [[CallerDirectives]]; the platform-wide
 * aggregates (dashboard, top-content, active-users) expose no per-object data
 * and are left as-is.
 */
class AnalyticsRoutes(analyticsService: AnalyticsService):

  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    concat(
      // Dashboard Summary
      path("dashboard") {
        get {
          parameters("period".withDefault("7d")) { period =>
            onSuccess(analyticsService.getDashboardSummary(period)) { summary =>
              complete(summary)
            }
          }
        }
      },

      // User Activity
      pathPrefix("users") {
        path(Segment / "activity") { userId =>
          get {
            callerOwning(userId) { _ =>
              onSuccess(analyticsService.getUserActivity(userId)) { activity =>
                complete(activity)
              }
            }
          }
        }
      },

      // Document Analytics
      pathPrefix("documents") {
        path(Segment / "stats") { documentId =>
          get {
            callerId { caller =>
              onSuccess(analyticsService.getDocumentStatsFor(documentId, caller)) {
                case Some(stats) => complete(stats)
                case None =>
                  complete(StatusCodes.Forbidden, "caller is not authorized for this document")
              }
            }
          }
        }
      },

      // Top Content
      path("top-content") {
        get {
          parameters(
            "type".withDefault("documents"),
            "period".withDefault("7d"),
            "limit".as[Int].withDefault(10)
          ) { (contentType, period, limit) =>
            onSuccess(analyticsService.getTopContent(contentType, period, limit)) { response =>
              complete(response)
            }
          }
        }
      },

      // Active Users
      path("active-users") {
        get {
          parameters("period".withDefault("daily")) { period =>
            onSuccess(analyticsService.getActiveUsers(period)) { response =>
              complete(response)
            }
          }
        }
      },

      // Storage Usage
      path("storage") {
        get {
          parameters("user_id".optional) { requestedUserId =>
            callerSubject(requestedUserId) { caller =>
              onSuccess(analyticsService.getStorageUsage(Some(caller))) { response =>
                complete(response)
              }
            }
          }
        }
      },

      // Export Report
      path("export") {
        get {
          parameters(
            "format".withDefault("json"),
            "period".withDefault("7d")
          ) { (format, period) =>
            callerId { caller =>
              format match
                case "csv" =>
                  onSuccess(analyticsService.exportReport("csv", period, Some(caller))) { report =>
                    val csvContent = buildCsvContent(report.data)
                    complete(HttpEntity(ContentTypes.`text/plain(UTF-8)`, csvContent))
                  }
                case _ =>
                  onSuccess(analyticsService.exportReport("json", period, Some(caller))) { report =>
                    complete(report)
                  }
            }
          }
        }
      },
    )
  }

  private def buildCsvContent(data: List[Map[String, String]]): String =
    if data.isEmpty then "event_id,event_type,user_id,resource_id,resource_type,timestamp\n"
    else
      val headers = List("event_id", "event_type", "user_id", "resource_id", "resource_type", "timestamp")
      val headerLine = headers.mkString(",")
      val rows = data.map { row =>
        headers.map(h => escapeCsvField(row.getOrElse(h, ""))).mkString(",")
      }
      (headerLine :: rows).mkString("\n") + "\n"

  private def escapeCsvField(value: String): String =
    if value.contains(",") || value.contains("\"") || value.contains("\n") then
      "\"" + value.replace("\"", "\"\"") + "\""
    else value
