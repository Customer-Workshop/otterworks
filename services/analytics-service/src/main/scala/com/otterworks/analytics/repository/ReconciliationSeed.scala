package com.otterworks.analytics.repository

import com.otterworks.analytics.model.{AnalyticsEvent, EventType}

import java.time.Instant
import java.time.temporal.ChronoUnit

/**
 * Deterministic event set used to reconcile the "before" and "after" analytics
 * stores. Anchored just before "now" (microsecond precision) so every event
 * falls inside all query windows (daily…90d) and round-trips exactly through
 * both the PostgreSQL and Iceberg stores (both persist epoch-nanoseconds).
 */
object ReconciliationSeed:

  private val base: Instant = Instant.now().truncatedTo(ChronoUnit.MICROS).minusSeconds(3600)
  private def at(i: Int): Instant = base.plusSeconds(i.toLong).plusNanos(i.toLong * 1000L)

  val events: List[AnalyticsEvent] = List(
    AnalyticsEvent("e01", EventType.DocumentCreated, "user-1", "doc-1", "document", Map("title" -> "Alpha"), at(1)),
    AnalyticsEvent("e02", EventType.DocumentViewed, "user-2", "doc-1", "document", Map("title" -> "Alpha"), at(2)),
    AnalyticsEvent("e03", EventType.DocumentEdited, "user-1", "doc-1", "document", Map("title" -> "Alpha"), at(3)),
    AnalyticsEvent("e04", EventType.DocumentShared, "user-1", "doc-1", "document", Map.empty, at(4)),
    AnalyticsEvent("e05", EventType.DocumentCreated, "user-2", "doc-2", "document", Map("title" -> "Beta"), at(5)),
    AnalyticsEvent("e06", EventType.FileUploaded, "user-1", "file-1", "file", Map("title" -> "F1"), at(6)),
    AnalyticsEvent("e07", EventType.FileDownloaded, "user-3", "file-1", "file", Map.empty, at(7)),
    AnalyticsEvent("e08", EventType.CollabSessionStarted, "user-2", "sess-1", "session", Map.empty, at(8)),
    AnalyticsEvent("e09", EventType.StorageAllocated, "user-1", "file-1", "file", Map("bytes" -> "2048"), at(9)),
    AnalyticsEvent("e10", EventType.StorageAllocated, "user-2", "file-2", "file", Map("bytes" -> "1024"), at(10)),
    AnalyticsEvent("e11", EventType.StorageReleased, "user-1", "file-1", "file", Map("bytes" -> "512"), at(11)),
    AnalyticsEvent("e12", EventType.DocumentViewed, "user-3", "doc-2", "document", Map("title" -> "Beta"), at(12))
  )
