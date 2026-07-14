package com.otterworks.analytics.repository.iceberg

import com.otterworks.analytics.config.IcebergConfig
import com.otterworks.analytics.model.*
import com.otterworks.analytics.repository.{MetricsAggregator, MetricsRepository}

import org.apache.iceberg.{FileFormat, PartitionKey, Table}
import org.apache.iceberg.catalog.Catalog
import org.apache.iceberg.data.{GenericAppenderFactory, IcebergGenerics, Record}
import org.apache.iceberg.io.OutputFileFactory
import org.slf4j.LoggerFactory

import java.util.concurrent.atomic.AtomicLong
import scala.concurrent.{ExecutionContext, Future}
import scala.jdk.CollectionConverters.*
import scala.util.Using

/**
 * Metrics repository backed by an S3 + Apache Iceberg lakehouse — the
 * RE-ARCHITECT "after" for the analytics store.
 *
 * Events consumed from SQS (and the REST API) are written as Iceberg records
 * into the `<database>.<table>` table (Glue-cataloged, S3-stored in the cloud;
 * a local `file://` Hadoop catalog for the reconciliation harness). Query
 * responses are derived by reading the events back and applying the shared,
 * storage-agnostic [[MetricsAggregator]] — exactly as
 * [[com.otterworks.analytics.repository.PostgresMetricsRepository]] does over
 * PostgreSQL — so the two backends return byte-for-byte identical analytics for
 * the same event set. That shared aggregator is what makes the migration a
 * verifiable adapter swap rather than a rewrite.
 *
 * Read-back transport is either a direct Iceberg table scan (default) or an
 * Amazon Athena query over the same Iceberg table (`athena.enabled`); both
 * observe identical data, so the dashboard "reads back via Athena" without any
 * change to the aggregation semantics or response schemas.
 */
class IcebergMetricsRepository(
    catalog: Catalog,
    table: Table,
    config: IcebergConfig,
    athenaReader: Option[AthenaEventReader] = None
)(using ec: ExecutionContext)
    extends MetricsRepository:

  private val logger = LoggerFactory.getLogger(getClass)

  // Monotonic insertion sequence, the Iceberg analogue of Postgres' BIGSERIAL.
  // Seeded from the max persisted `seq` so it keeps increasing across restarts.
  private val seqCounter: AtomicLong = new AtomicLong(scanMaxSeq())
  // Distinct file names per writer, per event.
  private val fileCounter: AtomicLong = new AtomicLong(0L)

  private def scanMaxSeq(): Long =
    table.refresh()
    Using.resource(IcebergGenerics.read(table).select("seq").build()) { records =>
      records.iterator().asScala.foldLeft(0L) { (max, r) =>
        math.max(max, r.getField("seq").asInstanceOf[Long])
      }
    }

  def storeEvent(event: AnalyticsEvent): Future[Unit] = Future {
    val seq = seqCounter.incrementAndGet()
    val record = IcebergSchema.toRecord(event, seq)

    val partitionKey = new PartitionKey(table.spec(), table.schema())
    partitionKey.partition(record)

    val fileFactory = OutputFileFactory
      .builderFor(table, 0, fileCounter.incrementAndGet())
      .format(FileFormat.PARQUET)
      .build()
    val outputFile = fileFactory.newOutputFile(partitionKey)

    val appenderFactory = new GenericAppenderFactory(table.schema(), table.spec())
    val dataWriter = appenderFactory.newDataWriter(outputFile, FileFormat.PARQUET, partitionKey)
    try dataWriter.write(record)
    finally dataWriter.close()

    table.newAppend().appendFile(dataWriter.toDataFile).commit()
    logger.debug("Wrote Iceberg event {} (seq={}) of type {}", event.eventId, seq, event.eventType)
  }

  /** Load the full event log in insertion order (matches the durable store). */
  private def loadAll(): Future[Seq[AnalyticsEvent]] =
    athenaReader match
      case Some(reader) => reader.loadAll()
      case None         => Future(scanAll())

  private def scanAll(): Seq[AnalyticsEvent] =
    table.refresh()
    Using.resource(IcebergGenerics.read(table).build()) { records =>
      records
        .iterator()
        .asScala
        .map((r: Record) => IcebergSchema.fromRecord(r))
        .toVector
        .sortBy(_._1)
        .map(_._2)
    }

  def getDashboardSummary(period: String): Future[DashboardSummary] =
    loadAll().map(MetricsAggregator.dashboardSummary(_, period))

  def getUserActivity(userId: String): Future[UserActivity] =
    loadAll().map(MetricsAggregator.userActivity(_, userId))

  def getDocumentStats(documentId: String): Future[DocumentStats] =
    loadAll().map(MetricsAggregator.documentStats(_, documentId))

  def getTopContent(contentType: String, period: String, limit: Int): Future[TopContentResponse] =
    loadAll().map(MetricsAggregator.topContent(_, contentType, period, limit))

  def getActiveUsers(period: String): Future[ActiveUsersResponse] =
    loadAll().map(MetricsAggregator.activeUsers(_, period))

  def getStorageUsage(userId: Option[String]): Future[StorageUsageResponse] =
    loadAll().map(MetricsAggregator.storageUsage(_, userId))

  def getExportData(period: String): Future[List[Map[String, String]]] =
    loadAll().map(MetricsAggregator.exportData(_, period))

  def getEventCount: Future[Long] =
    loadAll().map(_.size.toLong)

object IcebergMetricsRepository:
  /**
   * Build a repository that reads via a direct Iceberg table scan: create the
   * selected catalog (Glue or a local Hadoop file catalog) and ensure the events
   * table exists. Used by local runs and the reconciliation harness; the Athena
   * read transport is wired explicitly in `Main` where the AWS config is
   * available.
   */
  def build(config: IcebergConfig)(using ec: ExecutionContext): IcebergMetricsRepository =
    val catalog = IcebergCatalogFactory.create(config)
    val table = IcebergCatalogFactory.ensureTable(catalog, config)
    new IcebergMetricsRepository(catalog, table, config, athenaReader = None)
