package com.otterworks.analytics.model

import spray.json.*

/**
 * Aggregated usage metrics for a single calendar day (UTC), produced by the
 * nightly usage-rollup batch job. One record per day that had at least one event.
 */
final case class DailyUsageRollup(
    date: String, // ISO-8601 calendar date (yyyy-MM-dd), UTC
    totalEvents: Long,
    activeUsers: Long,
    documentsCreated: Long,
    documentsViewed: Long,
    documentsEdited: Long,
    filesUploaded: Long,
    filesDownloaded: Long,
    collabSessions: Long,
    storageAllocatedBytes: Long,
    storageReleasedBytes: Long,
    netStorageBytes: Long
)

/**
 * Full output document of a single batch run: run metadata plus the per-day
 * rollups. The `rollups` list is deterministic for a given input; `generatedAt`
 * is the only non-deterministic field and is excluded from correctness checks.
 */
final case class UsageRollupReport(
    generatedAt: String,
    source: String,
    windowStart: Option[String],
    windowEnd: Option[String],
    dayCount: Long,
    totalEvents: Long,
    rollups: List[DailyUsageRollup]
)

/** Spray JSON formats for the usage-rollup batch output. */
object UsageRollupJsonProtocol extends DefaultJsonProtocol:
  given dailyUsageRollupFormat: RootJsonFormat[DailyUsageRollup] =
    jsonFormat12(DailyUsageRollup.apply)

  given usageRollupReportFormat: RootJsonFormat[UsageRollupReport] =
    jsonFormat7(UsageRollupReport.apply)
