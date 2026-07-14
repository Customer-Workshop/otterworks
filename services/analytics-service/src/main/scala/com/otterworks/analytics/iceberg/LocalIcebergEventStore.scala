package com.otterworks.analytics.iceberg

import com.otterworks.analytics.config.IcebergConfig
import com.otterworks.analytics.db.DailyMetric
import com.otterworks.analytics.model.AnalyticsEvent
import org.slf4j.LoggerFactory
import spray.json.*
import spray.json.DefaultJsonProtocol.*

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths, StandardOpenOption}
import scala.concurrent.{ExecutionContext, Future}
import scala.jdk.CollectionConverters.*

/**
 * Dependency-light, on-disk stand-in for the S3 + Iceberg table.
 *
 * It lays out the *same* Iceberg column schema (see [[IcebergRow]]) under a
 * warehouse directory, partitioned by `event_type` exactly like the Athena
 * table, one data file per appended row:
 *
 *   {localWarehouse}/{database}/{table}/data/event_type={type}/{seq}.row.json
 *
 * Every row crosses the shared [[IcebergRowCodec]] serialization boundary
 * (metadata JSON + epoch-nanos timestamp), so parity proven here is parity of
 * the storage encoding the Athena path also uses. This is the local/in-cluster
 * stand-in the migration falls back to when Athena is not reachable from the
 * runtime path; the real cloud path is [[AthenaIcebergEventStore]].
 */
class LocalIcebergEventStore(config: IcebergConfig)(using ec: ExecutionContext) extends IcebergEventStore:
  private val logger = LoggerFactory.getLogger(getClass)
  private val lock = new Object

  private val tableRoot: Path =
    Paths.get(config.localWarehouse, config.database, config.eventsTable)
  private val dataDir: Path = tableRoot.resolve("data")
  private val aggregatesDir: Path =
    Paths.get(config.localWarehouse, config.database, config.aggregatesTable, "data")

  private given rowFormat: RootJsonFormat[IcebergRow] = jsonFormat9(IcebergRow.apply)

  private def partitionDir(eventType: String): Path =
    dataDir.resolve(s"event_type=${sanitize(eventType)}")

  private def sanitize(s: String): String = s.replaceAll("[^A-Za-z0-9._-]", "_")

  def ensureTable(): Future[Unit] = Future {
    lock.synchronized(Files.createDirectories(dataDir))
    logger.info("Local Iceberg warehouse ready at {}", tableRoot)
  }

  def append(seqNo: Long, event: AnalyticsEvent): Future[Unit] = Future {
    val row = IcebergRowCodec.toRow(seqNo, event)
    lock.synchronized {
      val dir = partitionDir(event.eventType)
      Files.createDirectories(dir)
      val file = dir.resolve(f"$seqNo%019d.row.json")
      Files.write(
        file,
        row.toJson.compactPrint.getBytes(StandardCharsets.UTF_8),
        StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE
      )
    }
  }

  private def readRows(): Seq[IcebergRow] =
    lock.synchronized {
      if !Files.exists(dataDir) then Seq.empty
      else
        val stream = Files.walk(dataDir)
        try
          stream.iterator().asScala
            .filter(p => Files.isRegularFile(p) && p.getFileName.toString.endsWith(".row.json"))
            .map(p => new String(Files.readAllBytes(p), StandardCharsets.UTF_8).parseJson.convertTo[IcebergRow])
            .toVector
        finally stream.close()
    }

  def loadAll(): Future[Seq[AnalyticsEvent]] = Future {
    readRows().sortBy(_.seqNo).map(IcebergRowCodec.toEvent)
  }

  def maxSeqNo(): Future[Long] = Future {
    val rows = readRows()
    if rows.isEmpty then 0L else rows.map(_.seqNo).max
  }

  override def count()(using ExecutionContext): Future[Long] = Future(readRows().size.toLong)

  override def dailyRollup()(using ExecutionContext): Future[Seq[DailyMetric]] =
    super.dailyRollup().map { metrics =>
      lock.synchronized {
        Files.createDirectories(aggregatesDir)
        metrics.foreach { metric =>
          val file = aggregatesDir.resolve(s"${metric.eventDate}--${sanitize(metric.eventType)}.row.json")
          val json = JsObject(
            "event_date" -> JsString(metric.eventDate),
            "event_type" -> JsString(metric.eventType),
            "event_count" -> JsNumber(metric.eventCount)
          ).compactPrint
          Files.write(
            file,
            json.getBytes(StandardCharsets.UTF_8),
            StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE
          )
        }
      }
      metrics
    }
