package com.otterworks.analytics.repository.iceberg

import com.otterworks.analytics.model.AnalyticsEvent

import org.apache.iceberg.{PartitionSpec, Schema}
import org.apache.iceberg.data.{GenericRecord, Record}
import org.apache.iceberg.types.Types

import java.time.{Instant, ZoneOffset}
import scala.jdk.CollectionConverters.*

/**
 * Iceberg table schema and record mapping for the analytics lakehouse.
 *
 * The table mirrors the durable PostgreSQL "before" store field-for-field:
 *  - `seq` is a monotonic insertion sequence, the Iceberg analogue of the
 *    Postgres `BIGSERIAL id`, so reads can preserve group-wise "first seen"
 *    ordering exactly (see [[com.otterworks.analytics.repository.MetricsAggregator]]).
 *  - `occurred_at` is epoch-nanoseconds (UTC), identical to the Postgres column,
 *    so the ISO-8601 timestamp echoed in responses round-trips byte-for-byte.
 *  - `event_date` / `event_type` are the identity partition columns, matching
 *    the "partitioned by event_date / event_type" lakehouse design.
 */
object IcebergSchema:

  val schema: Schema = new Schema(
    Types.NestedField.required(1, "seq", Types.LongType.get()),
    Types.NestedField.required(2, "event_id", Types.StringType.get()),
    Types.NestedField.required(3, "event_type", Types.StringType.get()),
    Types.NestedField.required(4, "user_id", Types.StringType.get()),
    Types.NestedField.required(5, "resource_id", Types.StringType.get()),
    Types.NestedField.required(6, "resource_type", Types.StringType.get()),
    Types.NestedField.optional(
      7,
      "metadata",
      Types.MapType.ofOptional(8, 9, Types.StringType.get(), Types.StringType.get())
    ),
    Types.NestedField.required(10, "occurred_at", Types.LongType.get()),
    Types.NestedField.required(11, "event_date", Types.StringType.get())
  )

  val spec: PartitionSpec =
    PartitionSpec.builderFor(schema).identity("event_date").identity("event_type").build()

  private def toEpochNanos(i: Instant): Long = i.getEpochSecond * 1000000000L + i.getNano
  private def fromEpochNanos(n: Long): Instant = Instant.ofEpochSecond(n / 1000000000L, n % 1000000000L)

  def eventDate(i: Instant): String = i.atZone(ZoneOffset.UTC).toLocalDate.toString

  /** Build an Iceberg [[Record]] for an event at the given insertion sequence. */
  def toRecord(event: AnalyticsEvent, seq: Long): Record =
    val record = GenericRecord.create(schema)
    record.setField("seq", seq)
    record.setField("event_id", event.eventId)
    record.setField("event_type", event.eventType)
    record.setField("user_id", event.userId)
    record.setField("resource_id", event.resourceId)
    record.setField("resource_type", event.resourceType)
    record.setField("metadata", event.metadata.asJava)
    record.setField("occurred_at", toEpochNanos(event.timestamp))
    record.setField("event_date", eventDate(event.timestamp))
    record

  /** Reconstruct an [[AnalyticsEvent]] and its insertion sequence from a record. */
  def fromRecord(record: Record): (Long, AnalyticsEvent) =
    val seq = record.getField("seq").asInstanceOf[Long]
    val metadata = record.getField("metadata") match
      case null                     => Map.empty[String, String]
      case m: java.util.Map[?, ?] => m.asScala.map { case (k, v) => k.toString -> v.toString }.toMap
      case _                        => Map.empty[String, String]
    val event = AnalyticsEvent(
      eventId = record.getField("event_id").toString,
      eventType = record.getField("event_type").toString,
      userId = record.getField("user_id").toString,
      resourceId = record.getField("resource_id").toString,
      resourceType = record.getField("resource_type").toString,
      metadata = metadata,
      timestamp = fromEpochNanos(record.getField("occurred_at").asInstanceOf[Long])
    )
    seq -> event
