package com.otterworks.analytics.repository

import com.otterworks.analytics.iceberg.IcebergEventStore
import com.otterworks.analytics.model.*
import org.slf4j.LoggerFactory

import java.time.Instant
import java.util.concurrent.atomic.AtomicLong
import scala.concurrent.{ExecutionContext, Future}

/**
 * MetricsRepository adapter backed by an S3 + Apache Iceberg event log.
 *
 * Storage concerns stop at [[IcebergEventStore]]; every API response is derived
 * with the same [[MetricsAggregator]] used by the golden PostgreSQL adapter.
 * This is the contract-preserving seam for the lakehouse migration.
 *
 * `seq_no` is a monotonic epoch-nanosecond ingest sequence. The deployment
 * wiring intentionally runs one Iceberg-backed writer replica because Athena
 * Iceberg INSERTs are serialized and do not provide a database sequence. Reads
 * sort by this value, retaining the PostgreSQL serial-id insertion semantics.
 */
class IcebergMetricsRepository(store: IcebergEventStore)(using ec: ExecutionContext) extends MetricsRepository:
  private val logger = LoggerFactory.getLogger(getClass)

  private final case class State(lastSequence: AtomicLong, eventCount: AtomicLong)

  private val initialized: Future[State] =
    for
      _ <- store.ensureTable()
      max <- store.maxSeqNo()
      count <- store.count()
    yield State(new AtomicLong(Math.max(max, nowNanos())), new AtomicLong(count))

  /** Fail-fast startup hook: proves the selected Iceberg table is reachable. */
  def initialize(): Future[Unit] = initialized.map(_ => ())

  private def nowNanos(): Long =
    val now = Instant.now()
    now.getEpochSecond * 1000000000L + now.getNano

  private def nextSequence(counter: AtomicLong): Long =
    counter.updateAndGet(previous => Math.max(previous + 1L, nowNanos()))

  private def loadAll(): Future[Seq[AnalyticsEvent]] =
    initialized.flatMap(_ => store.loadAll())

  def storeEvent(event: AnalyticsEvent): Future[Unit] =
    initialized.flatMap { state =>
      val seqNo = nextSequence(state.lastSequence)
      store.append(seqNo, event).map { _ =>
        state.eventCount.incrementAndGet()
        logger.debug("Stored Iceberg event {} of type {} at sequence {}", event.eventId, event.eventType, seqNo)
      }
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
    initialized.map(_.eventCount.get())

  def getDailyMetrics = store.dailyRollup()

  def close(): Unit = store.close()
