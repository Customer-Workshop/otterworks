package com.otterworks.analytics.iceberg

import com.otterworks.analytics.config.{AwsConfig, IcebergConfig}
import com.otterworks.analytics.db.DailyMetric
import com.otterworks.analytics.model.AnalyticsEvent
import org.slf4j.LoggerFactory
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.athena.AthenaClient
import software.amazon.awssdk.services.athena.model.*

import java.net.URI
import scala.concurrent.{ExecutionContext, Future, blocking}
import scala.jdk.CollectionConverters.*

/**
 * The real cloud path for the analytics lakehouse: reads and writes the Glue
 * catalog Iceberg table on S3 via Amazon Athena.
 *
 * Writes use `INSERT INTO ... VALUES` and reads use `SELECT ... ORDER BY
 * seq_no`; the table is created with `TBLPROPERTIES('table_type'='ICEBERG')`.
 * Rows cross the shared [[IcebergRowCodec]] boundary so the reconstructed
 * events feed [[com.otterworks.analytics.repository.MetricsAggregator]]
 * identically to the PostgreSQL store.
 *
 * All Athena calls are synchronous JDBC-style poll loops wrapped in `Future`
 * on the provided execution context; Athena SELECT latency makes this suitable
 * for the reconciliation/validation harness and batch reads rather than a hot
 * per-request path.
 */
class AthenaIcebergEventStore(config: IcebergConfig, aws: AwsConfig)(using ec: ExecutionContext)
    extends IcebergEventStore:

  private val logger = LoggerFactory.getLogger(getClass)

  private lazy val client: AthenaClient =
    val b = AthenaClient.builder().region(Region.of(aws.region))
    aws.endpointUrl.filter(_.nonEmpty).foreach(u => b.endpointOverride(URI.create(u)))
    b.build()

  private val fqTable = s"${config.database}.${config.eventsTable}"
  private val fqAggregatesTable = s"${config.database}.${config.aggregatesTable}"

  private def startAndAwait(sql: String): String =
    val ctx = QueryExecutionContext.builder().database(config.database).build()
    val resultConf = ResultConfiguration.builder().outputLocation(config.athenaOutput).build()
    val start = StartQueryExecutionRequest.builder()
      .queryString(sql)
      .workGroup(config.athenaWorkgroup)
      .queryExecutionContext(ctx)
      .resultConfiguration(resultConf)
      .build()
    val id = client.startQueryExecution(start).queryExecutionId()
    awaitCompletion(id)
    id

  private def awaitCompletion(id: String): Unit =
    var done = false
    while !done do
      val exec = client.getQueryExecution(
        GetQueryExecutionRequest.builder().queryExecutionId(id).build()).queryExecution()
      exec.status().state() match
        case QueryExecutionState.SUCCEEDED => done = true
        case QueryExecutionState.FAILED | QueryExecutionState.CANCELLED =>
          val reason = Option(exec.status().stateChangeReason()).getOrElse("unknown")
          throw new RuntimeException(s"Athena query $id ${exec.status().state()}: $reason")
        case _ => Thread.sleep(500)

  /** Execute a statement that returns no useful rows (DDL / DML). */
  private def execute(sql: String): Future[Unit] = Future(blocking(startAndAwait(sql))).map(_ => ())

  /** Execute a SELECT and return result rows as ordered lists of string cells. */
  private def query(sql: String): Future[Seq[Seq[String]]] = Future(blocking {
    val id = startAndAwait(sql)
    val rows = Vector.newBuilder[Seq[String]]
    var token: Option[String] = None
    var first = true
    var more = true
    while more do
      val req = GetQueryResultsRequest.builder().queryExecutionId(id)
      token.foreach(req.nextToken)
      val resp = client.getQueryResults(req.build())
      val rs = resp.resultSet().rows().asScala.toList
      val dataRows = if first then rs.drop(1) else rs // first page: skip header row
      first = false
      dataRows.foreach { r =>
        rows += r.data().asScala.toVector.map(d => Option(d.varCharValue()).getOrElse(""))
      }
      token = Option(resp.nextToken())
      more = token.isDefined
    rows.result()
  })

  def ensureTable(): Future[Unit] =
    for
      _ <- query(s"SELECT seq_no FROM $fqTable LIMIT 0")
      _ <- query(s"SELECT event_date FROM $fqAggregatesTable LIMIT 0")
    yield logger.info("Athena Iceberg tables {} and {} ready", fqTable, fqAggregatesTable)

  def append(seqNo: Long, event: AnalyticsEvent): Future[Unit] =
    val r = IcebergRowCodec.toRow(seqNo, event)
    val values = List(
      r.seqNo.toString,
      IcebergRowCodec.sqlLiteral(r.eventId),
      IcebergRowCodec.sqlLiteral(r.eventType),
      IcebergRowCodec.sqlLiteral(r.userId),
      IcebergRowCodec.sqlLiteral(r.resourceId),
      IcebergRowCodec.sqlLiteral(r.resourceType),
      IcebergRowCodec.sqlLiteral(r.metadata),
      r.occurredAt.toString,
      IcebergRowCodec.sqlLiteral(r.eventDate)
    ).mkString(", ")
    execute(s"INSERT INTO $fqTable (${IcebergRowCodec.columns.mkString(", ")}) VALUES ($values)")

  def loadAll(): Future[Seq[AnalyticsEvent]] =
    val cols = "seq_no, event_id, event_type, user_id, resource_id, resource_type, metadata, occurred_at, event_date"
    query(s"SELECT $cols FROM $fqTable ORDER BY seq_no ASC").map { rows =>
      rows.map { c =>
        IcebergRowCodec.toEvent(IcebergRow(
          seqNo = c(0).toLong,
          eventId = c(1),
          eventType = c(2),
          userId = c(3),
          resourceId = c(4),
          resourceType = c(5),
          metadata = c(6),
          occurredAt = c(7).toLong,
          eventDate = c(8)
        ))
      }
    }

  def maxSeqNo(): Future[Long] =
    query(s"SELECT COALESCE(MAX(seq_no), 0) FROM $fqTable").map { rows =>
      rows.headOption.flatMap(_.headOption).filter(_.nonEmpty).map(_.toLong).getOrElse(0L)
    }

  override def count()(using ExecutionContext): Future[Long] =
    query(s"SELECT COUNT(*) FROM $fqTable").map { rows =>
      rows.headOption.flatMap(_.headOption).filter(_.nonEmpty).map(_.toLong).getOrElse(0L)
    }

  override def dailyRollup()(using ExecutionContext): Future[Seq[DailyMetric]] =
    val refresh =
      s"""MERGE INTO $fqAggregatesTable AS target
         |USING (
         |  SELECT event_date, event_type, COUNT(*) AS event_count
         |  FROM $fqTable
         |  GROUP BY event_date, event_type
         |) AS source
         |ON target.event_date = source.event_date
         |AND target.event_type = source.event_type
         |WHEN MATCHED THEN UPDATE SET event_count = source.event_count
         |WHEN NOT MATCHED THEN INSERT (event_date, event_type, event_count)
         |VALUES (source.event_date, source.event_type, source.event_count)""".stripMargin
    execute(refresh).flatMap { _ =>
      query(s"SELECT event_date, event_type, event_count FROM $fqAggregatesTable ORDER BY event_date, event_type")
    }.map(_.map(c => DailyMetric(c(0), c(1), c(2).toLong)))

  override def close(): Unit = client.close()
