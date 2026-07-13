package com.otterworks.analytics.batch

import com.otterworks.analytics.model.*
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

import java.time.Instant

class UsageRollupAggregatorSpec extends AnyFlatSpec with Matchers:

  private def event(
      eventType: String,
      userId: String,
      timestamp: String,
      resourceType: String = "document",
      metadata: Map[String, String] = Map.empty
  ): AnalyticsEvent =
    AnalyticsEvent(
      eventId = s"$eventType-$userId-$timestamp",
      eventType = eventType,
      userId = userId,
      resourceId = "res-1",
      resourceType = resourceType,
      metadata = metadata,
      timestamp = Instant.parse(timestamp)
    )

  "UsageRollupAggregator" should "produce one rollup per UTC day, sorted ascending" in {
    val events = Seq(
      event(EventType.DocumentCreated, "u1", "2024-03-02T10:00:00Z"),
      event(EventType.DocumentCreated, "u2", "2024-03-01T10:00:00Z"),
      event(EventType.DocumentViewed, "u1", "2024-03-01T23:59:59Z")
    )

    val rollups = UsageRollupAggregator.rollup(events)

    rollups.map(_.date) shouldBe List("2024-03-01", "2024-03-02")
  }

  it should "count event types and distinct active users per day" in {
    val events = Seq(
      event(EventType.DocumentCreated, "u1", "2024-03-01T01:00:00Z"),
      event(EventType.DocumentCreated, "u2", "2024-03-01T02:00:00Z"),
      event(EventType.DocumentViewed, "u1", "2024-03-01T03:00:00Z"),
      event(EventType.FileUploaded, "u3", "2024-03-01T04:00:00Z", resourceType = "file"),
      event(EventType.CollabSessionStarted, "u1", "2024-03-01T05:00:00Z")
    )

    val Seq(day) = UsageRollupAggregator.rollup(events)

    day.totalEvents shouldBe 5L
    day.activeUsers shouldBe 3L
    day.documentsCreated shouldBe 2L
    day.documentsViewed shouldBe 1L
    day.filesUploaded shouldBe 1L
    day.collabSessions shouldBe 1L
  }

  it should "sum storage allocated/released bytes and compute the net" in {
    val events = Seq(
      event(EventType.StorageAllocated, "u1", "2024-03-01T01:00:00Z", "file", Map("bytes" -> "1000")),
      event(EventType.StorageAllocated, "u2", "2024-03-01T02:00:00Z", "file", Map("bytes" -> "500")),
      event(EventType.StorageReleased, "u1", "2024-03-01T03:00:00Z", "file", Map("bytes" -> "200"))
    )

    val Seq(day) = UsageRollupAggregator.rollup(events)

    day.storageAllocatedBytes shouldBe 1500L
    day.storageReleasedBytes shouldBe 200L
    day.netStorageBytes shouldBe 1300L
  }

  it should "tolerate missing or malformed byte metadata" in {
    val events = Seq(
      event(EventType.StorageAllocated, "u1", "2024-03-01T01:00:00Z", "file", Map.empty),
      event(EventType.StorageAllocated, "u2", "2024-03-01T02:00:00Z", "file", Map("bytes" -> "not-a-number"))
    )

    val Seq(day) = UsageRollupAggregator.rollup(events)

    day.storageAllocatedBytes shouldBe 0L
  }

  it should "return an empty list for no events" in {
    UsageRollupAggregator.rollup(Seq.empty) shouldBe empty
  }
