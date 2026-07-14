package com.otterworks.analytics.iceberg

import com.otterworks.analytics.model.AnalyticsEvent
import spray.json.*
import spray.json.DefaultJsonProtocol.*

import java.time.{Instant, ZoneOffset}

/**
 * The column projection of an [[AnalyticsEvent]] as it is physically stored in
 * the Iceberg `analytics_events` table (one row per event).
 *
 * The layout is intentionally flat and primitive-typed so it maps 1:1 onto both
 * Athena Iceberg columns and a local Parquet/NDJSON stand-in:
 *
 *   seq_no        bigint   monotonic insertion order (mirrors the Postgres serial id)
 *   event_id      string
 *   event_type    string   (Iceberg partition column)
 *   user_id       string
 *   resource_id   string
 *   resource_type string
 *   metadata      string   JSON object, encoded exactly as the PostgreSQL store does
 *   occurred_at   bigint   epoch-nanoseconds (UTC) — round-trips instants exactly
 *   event_date    string   YYYY-MM-DD (UTC) derived partition helper
 *
 * `IcebergRowCodec` is shared by every backend ([[AthenaIcebergEventStore]] and
 * [[LocalIcebergEventStore]]) so the serialization boundary crossed on the way
 * to S3/Iceberg is exercised identically regardless of where the bytes land.
 */
final case class IcebergRow(
    seqNo: Long,
    eventId: String,
    eventType: String,
    userId: String,
    resourceId: String,
    resourceType: String,
    metadata: String,
    occurredAt: Long,
    eventDate: String
)

object IcebergRowCodec:
  val columns: List[String] =
    List("seq_no", "event_id", "event_type", "user_id", "resource_id",
      "resource_type", "metadata", "occurred_at", "event_date")

  def encodeMetadata(m: Map[String, String]): String = m.toJson.compactPrint
  def decodeMetadata(s: String): Map[String, String] =
    if s == null || s.isEmpty then Map.empty else s.parseJson.convertTo[Map[String, String]]

  def toEpochNanos(i: Instant): Long = i.getEpochSecond * 1000000000L + i.getNano
  def fromEpochNanos(n: Long): Instant = Instant.ofEpochSecond(n / 1000000000L, n % 1000000000L)

  def toRow(seqNo: Long, e: AnalyticsEvent): IcebergRow =
    IcebergRow(
      seqNo = seqNo,
      eventId = e.eventId,
      eventType = e.eventType,
      userId = e.userId,
      resourceId = e.resourceId,
      resourceType = e.resourceType,
      metadata = encodeMetadata(e.metadata),
      occurredAt = toEpochNanos(e.timestamp),
      eventDate = e.timestamp.atZone(ZoneOffset.UTC).toLocalDate.toString
    )

  def toEvent(r: IcebergRow): AnalyticsEvent =
    AnalyticsEvent(
      eventId = r.eventId,
      eventType = r.eventType,
      userId = r.userId,
      resourceId = r.resourceId,
      resourceType = r.resourceType,
      metadata = decodeMetadata(r.metadata),
      timestamp = fromEpochNanos(r.occurredAt)
    )

  /** Escape a string for safe interpolation into an Athena SQL string literal. */
  def sqlLiteral(s: String): String = "'" + s.replace("'", "''") + "'"
