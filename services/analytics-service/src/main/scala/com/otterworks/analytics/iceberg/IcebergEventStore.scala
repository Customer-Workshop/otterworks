package com.otterworks.analytics.iceberg

import com.otterworks.analytics.config.{AwsConfig, IcebergConfig}
import com.otterworks.analytics.db.DailyMetric
import com.otterworks.analytics.model.AnalyticsEvent
import org.slf4j.LoggerFactory

import scala.concurrent.{ExecutionContext, Future}

/**
 * Physical read/write seam for the analytics lakehouse (S3 + Apache Iceberg).
 *
 * A store persists the raw event log as Iceberg rows and can read it back in
 * insertion order. [[IcebergMetricsRepository]] layers the storage-agnostic
 * [[com.otterworks.analytics.repository.MetricsAggregator]] on top, so the
 * query/response contract is identical to the PostgreSQL "before" state — the
 * migration is a storage/connection-layer swap, not an API change.
 *
 * Two implementations:
 *  - [[AthenaIcebergEventStore]] — the real cloud path: writes/reads the Glue
 *    catalog Iceberg table on S3 via Amazon Athena.
 *  - [[LocalIcebergEventStore]] — a dependency-light, on-disk stand-in that
 *    lays out the same Iceberg column schema under a warehouse directory, used
 *    for the reconciliation harness and the in-cluster/local flow proof when
 *    Athena is not reachable from the runtime path.
 */
trait IcebergEventStore:
  /** Ensure the Glue database + Iceberg table (or local warehouse) exist. */
  def ensureTable(): Future[Unit]

  /** Append one event at the given monotonic sequence number. */
  def append(seqNo: Long, event: AnalyticsEvent): Future[Unit]

  /** The full event log, ordered by seq_no ascending (insertion order). */
  def loadAll(): Future[Seq[AnalyticsEvent]]

  /** Highest seq_no currently stored, or 0 if empty (for the next append). */
  def maxSeqNo(): Future[Long]

  /** Number of rows currently stored (seed value for the health counter). */
  def count()(using ec: ExecutionContext): Future[Long] = loadAll().map(_.size.toLong)

  /** Daily aggregate rollup derived from the stored rows (reconciliation). */
  def dailyRollup()(using ec: ExecutionContext): Future[Seq[DailyMetric]] =
    loadAll().map { events =>
      events
        .groupBy(e => (e.timestamp.atZone(java.time.ZoneOffset.UTC).toLocalDate.toString, e.eventType))
        .map { case ((date, tpe), es) => DailyMetric(date, tpe, es.size.toLong) }
        .toSeq
        .sortBy(m => (m.eventDate, m.eventType))
    }

  def close(): Unit = ()

object IcebergEventStore:
  private val logger = LoggerFactory.getLogger(getClass)

  /** Build the store selected by `iceberg.mode` (athena | local). */
  def fromConfig(iceberg: IcebergConfig, aws: AwsConfig)(using ec: ExecutionContext): IcebergEventStore =
    iceberg.mode.trim.toLowerCase match
      case "local" =>
        logger.info("Iceberg store: LOCAL warehouse stand-in at {}", iceberg.localWarehouse)
        new LocalIcebergEventStore(iceberg)
      case _ =>
        logger.info(
          "Iceberg store: Athena over S3/Glue (database={}, table={}, workgroup={})",
          iceberg.database, iceberg.eventsTable, iceberg.athenaWorkgroup)
        new AthenaIcebergEventStore(iceberg, aws)
