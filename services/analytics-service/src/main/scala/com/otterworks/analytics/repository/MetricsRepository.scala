package com.otterworks.analytics.repository

import com.otterworks.analytics.config.PostgresConfig
import com.otterworks.analytics.model.*
import org.slf4j.LoggerFactory

import java.time.{Instant, LocalDate, ZoneOffset}
import java.time.format.DateTimeFormatter
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import scala.collection.concurrent.TrieMap
import scala.collection.mutable
import scala.concurrent.{ExecutionContext, Future}

/**
 * In-memory metrics repository that stores aggregated analytics data.
 *
 * In production, this would be backed by PostgreSQL via Slick. The in-memory
 * implementation allows the service to compile and run without requiring a
 * live database connection, making local development and testing easier.
 */
class MetricsRepository(config: PostgresConfig)(using ec: ExecutionContext):

  private val logger = LoggerFactory.getLogger(getClass)

  // In-memory stores for events and aggregated metrics
  private val events = mutable.ListBuffer.empty[AnalyticsEvent]
  private val lock = new Object

  def storeEvent(event: AnalyticsEvent): Future[Unit] = Future {
    lock.synchronized {
      events += event
    }
    logger.debug("Stored event {} of type {}", event.eventId, event.eventType)
  }

  def getDashboardSummary(period: String): Future[DashboardSummary] = Future {
    val cutoff = periodToCutoff(period)
    lock.synchronized {
      val filtered = events.filter(_.timestamp.isAfter(cutoff))
      DashboardSummary(
        period = period,
        dailyActiveUsers = filtered.map(_.userId).distinct.size.toLong,
        documentsCreated = filtered.count(_.eventType == EventType.DocumentCreated).toLong,
        filesUploaded = filtered.count(_.eventType == EventType.FileUploaded).toLong,
        storageUsedBytes = Math.max(0L, filtered
          .filter(e => e.eventType == EventType.StorageAllocated || e.eventType == EventType.StorageReleased)
          .foldLeft(0L) { (acc, e) =>
            val bytes = e.metadata.getOrElse("bytes", "0").toLong
            if e.eventType == EventType.StorageAllocated then acc + bytes else acc - bytes
          }),
        collabSessions = filtered.count(_.eventType == EventType.CollabSessionStarted).toLong,
        totalEvents = filtered.size.toLong
      )
    }
  }

  def getUserActivity(userId: String): Future[UserActivity] = Future {
    lock.synchronized {
      val userEvents = events.filter(_.userId == userId)
      val recent = userEvents.sortBy(_.timestamp)(using Ordering[Instant].reverse).take(20)
      UserActivity(
        userId = userId,
        totalEvents = userEvents.size.toLong,
        documentsCreated = userEvents.count(_.eventType == EventType.DocumentCreated).toLong,
        documentsViewed = userEvents.count(_.eventType == EventType.DocumentViewed).toLong,
        documentsEdited = userEvents.count(_.eventType == EventType.DocumentEdited).toLong,
        filesUploaded = userEvents.count(_.eventType == EventType.FileUploaded).toLong,
        filesDownloaded = userEvents.count(_.eventType == EventType.FileDownloaded).toLong,
        lastActiveAt = recent.headOption.map(_.timestamp.toString),
        recentEvents = recent.map(e =>
          EventSummary(
            eventId = e.eventId,
            eventType = e.eventType,
            resourceId = e.resourceId,
            resourceType = e.resourceType,
            timestamp = e.timestamp.toString
          )
        ).toList
      )
    }
  }

  def getDocumentStats(documentId: String): Future[DocumentStats] = Future {
    lock.synchronized {
      val docEvents = events.filter(_.resourceId == documentId)
      val views = docEvents.filter(_.eventType == EventType.DocumentViewed)
      val edits = docEvents.filter(_.eventType == EventType.DocumentEdited)
      val shares = docEvents.filter(_.eventType == EventType.DocumentShared)
      DocumentStats(
        documentId = documentId,
        views = views.size.toLong,
        edits = edits.size.toLong,
        shares = shares.size.toLong,
        uniqueViewers = views.map(_.userId).distinct.size.toLong,
        lastViewedAt = views.sortBy(_.timestamp)(using Ordering[Instant].reverse).headOption.map(_.timestamp.toString),
        lastEditedAt = edits.sortBy(_.timestamp)(using Ordering[Instant].reverse).headOption.map(_.timestamp.toString)
      )
    }
  }

  def getTopContent(contentType: String, period: String, limit: Int): Future[TopContentResponse] = Future {
    val cutoff = periodToCutoff(period)
    lock.synchronized {
      val resourceTypeFilter = contentType match
        case "documents" => Set("document")
        case "files"     => Set("file")
        case _           => Set("document", "file")

      val filtered = events
        .filter(e => e.timestamp.isAfter(cutoff) && resourceTypeFilter.contains(e.resourceType))

      val grouped = filtered.groupBy(_.resourceId)
      val items = grouped.toList
        .map { case (resourceId, resourceEvents) =>
          ContentItem(
            resourceId = resourceId,
            resourceType = resourceEvents.head.resourceType,
            title = resourceEvents.head.metadata.getOrElse("title", resourceId),
            eventCount = resourceEvents.size.toLong,
            uniqueUsers = resourceEvents.map(_.userId).distinct.size.toLong
          )
        }
        .sortBy(-_.eventCount)
        .take(limit)

      TopContentResponse(
        period = period,
        contentType = contentType,
        items = items
      )
    }
  }

  def getActiveUsers(period: String): Future[ActiveUsersResponse] = Future {
    val cutoff = periodToCutoff(period)
    lock.synchronized {
      val filtered = events.filter(_.timestamp.isAfter(cutoff))
      val grouped = filtered.groupBy(_.userId)
      val users = grouped.toList
        .map { case (userId, userEvents) =>
          ActiveUser(
            userId = userId,
            eventCount = userEvents.size.toLong,
            lastActiveAt = userEvents.maxBy(_.timestamp).timestamp.toString
          )
        }
        .sortBy(-_.eventCount)

      ActiveUsersResponse(
        period = period,
        count = users.size.toLong,
        users = users
      )
    }
  }

  def getStorageUsage(userId: Option[String]): Future[StorageUsageResponse] = Future {
    lock.synchronized {
      val filtered = userId match
        case Some(uid) => events.filter(_.userId == uid)
        case None      => events.toSeq

      val storageEvents = filtered.filter(e =>
        e.eventType == EventType.StorageAllocated || e.eventType == EventType.StorageReleased
      )

      val totalBytes = storageEvents.foldLeft(0L) { (acc, e) =>
        val bytes = e.metadata.getOrElse("bytes", "0").toLong
        if e.eventType == EventType.StorageAllocated then acc + bytes else acc - bytes
      }

      val filesCount = filtered.count(_.eventType == EventType.FileUploaded).toLong
      val docsCount = filtered.count(_.eventType == EventType.DocumentCreated).toLong

      val breakdownByType = filtered
        .filter(e => e.eventType == EventType.StorageAllocated)
        .groupBy(_.resourceType)
        .map { case (rt, evts) =>
          rt -> evts.flatMap(_.metadata.get("bytes").map(_.toLong)).sum
        }
        .toMap

      StorageUsageResponse(
        userId = userId,
        totalStorageBytes = Math.max(0L, totalBytes),
        filesCount = filesCount,
        documentsCount = docsCount,
        breakdownByType = breakdownByType
      )
    }
  }

  def getExportData(period: String): Future[List[Map[String, String]]] = Future {
    val cutoff = periodToCutoff(period)
    lock.synchronized {
      events
        .filter(_.timestamp.isAfter(cutoff))
        .sortBy(_.timestamp)(using Ordering[Instant].reverse)
        .map { e =>
          Map(
            "event_id" -> e.eventId,
            "event_type" -> e.eventType,
            "user_id" -> e.userId,
            "resource_id" -> e.resourceId,
            "resource_type" -> e.resourceType,
            "timestamp" -> e.timestamp.toString
          )
        }
        .toList
    }
  }

  def getEventCount: Future[Long] = Future {
    lock.synchronized {
      events.size.toLong
    }
  }

  private def periodToCutoff(period: String): Instant =
    val now = Instant.now()
    period match
      case "7d"      => now.minusSeconds(7L * 24 * 3600)
      case "30d"     => now.minusSeconds(30L * 24 * 3600)
      case "90d"     => now.minusSeconds(90L * 24 * 3600)
      case "daily"   => now.minusSeconds(24L * 3600)
      case "weekly"  => now.minusSeconds(7L * 24 * 3600)
      case "monthly" => now.minusSeconds(30L * 24 * 3600)
      case _         => now.minusSeconds(7L * 24 * 3600)
