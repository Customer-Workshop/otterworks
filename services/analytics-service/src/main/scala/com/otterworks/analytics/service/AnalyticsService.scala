package com.otterworks.analytics.service

import com.otterworks.analytics.model.*
import com.otterworks.analytics.repository.MetricsRepository
import net.logstash.logback.argument.StructuredArguments.kv
import org.slf4j.LoggerFactory

import java.time.Instant
import scala.concurrent.{ExecutionContext, Future}

/**
 * Core analytics business logic. Coordinates event tracking with the
 * repository layer and provides query methods for all analytics endpoints.
 */
class AnalyticsService(repository: MetricsRepository)(using ec: ExecutionContext):

  private val logger = LoggerFactory.getLogger(getClass)

  /** Track a new analytics event and persist it. */
  def trackEvent(
      eventType: String,
      userId: String,
      resourceId: String,
      resourceType: String,
      metadata: Map[String, String]
  ): Future[AnalyticsEvent] =
    val event = AnalyticsEvent.create(eventType, userId, resourceId, resourceType, metadata)
    logger.info(
      "event_tracked",
      kv("event_id", event.eventId),
      kv("event_type", event.eventType),
      kv("user_id", event.userId),
      kv("resource_id", event.resourceId),
      kv("resource_type", event.resourceType),
    )
    repository.storeEvent(event).map(_ => event)

  /** Get aggregated dashboard metrics for the given period. */
  def getDashboardSummary(period: String): Future[DashboardSummary] =
    logger.debug("dashboard_summary_requested", kv("period", period))
    repository.getDashboardSummary(period)

  /** Get activity for a specific user. */
  def getUserActivity(userId: String): Future[UserActivity] =
    logger.debug("user_activity_requested", kv("user_id", userId))
    repository.getUserActivity(userId)

  /** Get analytics for a specific document. */
  def getDocumentStats(documentId: String): Future[DocumentStats] =
    logger.debug("document_stats_requested", kv("document_id", documentId))
    repository.getDocumentStats(documentId)

  /** Get top content ranked by activity. */
  def getTopContent(contentType: String, period: String, limit: Int = 10): Future[TopContentResponse] =
    logger.debug(
      "top_content_requested",
      kv("content_type", contentType),
      kv("period", period),
      kv("limit", limit))
    repository.getTopContent(contentType, period, limit)

  /** Get active users for the given period. */
  def getActiveUsers(period: String): Future[ActiveUsersResponse] =
    logger.debug("active_users_requested", kv("period", period))
    repository.getActiveUsers(period)

  /** Get storage usage, optionally filtered by user. */
  def getStorageUsage(userId: Option[String]): Future[StorageUsageResponse] =
    logger.debug("storage_usage_requested", kv("user_id", userId.orNull))
    repository.getStorageUsage(userId)

  /** Export analytics data for the given period. */
  def exportReport(format: String, period: String): Future[ExportReportResponse] =
    logger.info("report_export_requested", kv("format", format), kv("period", period))
    repository.getExportData(period).map { data =>
      ExportReportResponse(
        format = format,
        period = period,
        generatedAt = Instant.now().toString,
        recordCount = data.size.toLong,
        data = data
      )
    }

  /** Get the total event count (used for health/metrics). */
  def getEventCount: Future[Long] =
    repository.getEventCount
