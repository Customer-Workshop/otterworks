package com.otterworks.analytics.model

import spray.json.*

/** Aggregated metrics for a given period, served by GET /api/v1/analytics/dashboard. */
final case class DashboardSummary(
    period: String,
    dailyActiveUsers: Long,
    documentsCreated: Long,
    filesUploaded: Long,
    storageUsedBytes: Long,
    collabSessions: Long,
    totalEvents: Long
)

/** Per-user activity summary returned by GET /api/v1/analytics/users/{id}/activity. */
final case class UserActivity(
    userId: String,
    totalEvents: Long,
    documentsCreated: Long,
    documentsViewed: Long,
    documentsEdited: Long,
    filesUploaded: Long,
    filesDownloaded: Long,
    lastActiveAt: Option[String],
    recentEvents: List[EventSummary]
)

/** Lightweight event reference for activity feeds. */
final case class EventSummary(
    eventId: String,
    eventType: String,
    resourceId: String,
    resourceType: String,
    timestamp: String
)

/** Document-level analytics returned by GET /api/v1/analytics/documents/{id}/stats. */
final case class DocumentStats(
    documentId: String,
    views: Long,
    edits: Long,
    shares: Long,
    uniqueViewers: Long,
    lastViewedAt: Option[String],
    lastEditedAt: Option[String]
)

/** Item in the top-content listing. */
final case class ContentItem(
    resourceId: String,
    resourceType: String,
    title: String,
    eventCount: Long,
    uniqueUsers: Long
)

/** Response for GET /api/v1/analytics/top-content. */
final case class TopContentResponse(
    period: String,
    contentType: String,
    items: List[ContentItem]
)

/** Active user entry. */
final case class ActiveUser(
    userId: String,
    eventCount: Long,
    lastActiveAt: String
)

/** Response for GET /api/v1/analytics/active-users. */
final case class ActiveUsersResponse(
    period: String,
    count: Long,
    users: List[ActiveUser]
)

/** Storage usage response for GET /api/v1/analytics/storage. */
final case class StorageUsageResponse(
    userId: Option[String],
    totalStorageBytes: Long,
    filesCount: Long,
    documentsCount: Long,
    breakdownByType: Map[String, Long]
)

/** Export report metadata response for GET /api/v1/analytics/export. */
final case class ExportReportResponse(
    format: String,
    period: String,
    generatedAt: String,
    recordCount: Long,
    data: List[Map[String, String]]
)

/** Spray JSON formats for all dashboard/analytics response types. */
object DashboardJsonProtocol extends DefaultJsonProtocol:
  given dashboardSummaryFormat: RootJsonFormat[DashboardSummary] =
    jsonFormat7(DashboardSummary.apply)

  given eventSummaryFormat: RootJsonFormat[EventSummary] =
    jsonFormat5(EventSummary.apply)

  given userActivityFormat: RootJsonFormat[UserActivity] =
    jsonFormat9(UserActivity.apply)

  given documentStatsFormat: RootJsonFormat[DocumentStats] =
    jsonFormat7(DocumentStats.apply)

  given contentItemFormat: RootJsonFormat[ContentItem] =
    jsonFormat5(ContentItem.apply)

  given topContentResponseFormat: RootJsonFormat[TopContentResponse] =
    jsonFormat3(TopContentResponse.apply)

  given activeUserFormat: RootJsonFormat[ActiveUser] =
    jsonFormat3(ActiveUser.apply)

  given activeUsersResponseFormat: RootJsonFormat[ActiveUsersResponse] =
    jsonFormat3(ActiveUsersResponse.apply)

  given storageUsageResponseFormat: RootJsonFormat[StorageUsageResponse] =
    jsonFormat5(StorageUsageResponse.apply)

  given exportReportResponseFormat: RootJsonFormat[ExportReportResponse] =
    jsonFormat5(ExportReportResponse.apply)
