package com.otterworks.analytics.api

import akka.http.scaladsl.marshallers.sprayjson.SprayJsonSupport.*
import akka.http.scaladsl.model.{ContentTypes, HttpEntity, StatusCodes}
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
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
 */
class AnalyticsRoutes(analyticsService: AnalyticsService):

  private val DefaultPeriod = "7d"
  private val PeriodParam = "period"

  val routes: Route = pathPrefix("api" / "v1" / "analytics") {
    concat(
      // Dashboard Summary
      path("dashboard") {
        get {
          parameters(PeriodParam.withDefault(DefaultPeriod)) { period =>
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
            onSuccess(analyticsService.getUserActivity(userId)) { activity =>
              complete(activity)
            }
          }
        }
      },

      // Document Analytics
      pathPrefix("documents") {
        path(Segment / "stats") { documentId =>
          get {
            onSuccess(analyticsService.getDocumentStats(documentId)) { stats =>
              complete(stats)
            }
          }
        }
      },

      // Top Content
      path("top-content") {
        get {
          parameters(
            "type".withDefault("documents"),
            PeriodParam.withDefault(DefaultPeriod),
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
          parameters(PeriodParam.withDefault("daily")) { period =>
            onSuccess(analyticsService.getActiveUsers(period)) { response =>
              complete(response)
            }
          }
        }
      },

      // Storage Usage
      path("storage") {
        get {
          parameters("user_id".optional) { userId =>
            onSuccess(analyticsService.getStorageUsage(userId)) { response =>
              complete(response)
            }
          }
        }
      },

      // Export Report
      path("export") {
        get {
          parameters(
            "format".withDefault("json"),
            PeriodParam.withDefault(DefaultPeriod)
          ) { (format, period) =>
            format match
              case "csv" =>
                onSuccess(analyticsService.exportReport("csv", period)) { report =>
                  val csvContent = buildCsvContent(report.data)
                  complete(HttpEntity(ContentTypes.`text/plain(UTF-8)`, csvContent))
                }
              case _ =>
                onSuccess(analyticsService.exportReport("json", period)) { report =>
                  complete(report)
                }
          }
        }
      },
    )
  }

  private val CsvHeaders = List("event_id", "event_type", "user_id", "resource_id", "resource_type", "timestamp")

  private def buildCsvContent(data: List[Map[String, String]]): String =
    if data.isEmpty then CsvHeaders.mkString(",") + "\n"
    else
      val headerLine = CsvHeaders.mkString(",")
      val rows = data.map { row =>
        CsvHeaders.map(h => escapeCsvField(row.getOrElse(h, ""))).mkString(",")
      }
      (headerLine :: rows).mkString("\n") + "\n"

  private def escapeCsvField(value: String): String =
    if value.contains(",") || value.contains("\"") || value.contains("\n") then
      "\"" + value.replace("\"", "\"\"") + "\""
    else value
