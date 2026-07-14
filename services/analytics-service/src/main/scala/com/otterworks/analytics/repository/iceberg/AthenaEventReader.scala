package com.otterworks.analytics.repository.iceberg

import com.otterworks.analytics.config.{AwsConfig, IcebergConfig}
import com.otterworks.analytics.model.AnalyticsEvent
import org.slf4j.LoggerFactory
import spray.json.*
import spray.json.DefaultJsonProtocol.*
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.athena.AthenaClient
import software.amazon.awssdk.services.athena.model.*

import java.net.URI
import java.time.Instant
import scala.annotation.tailrec
import scala.concurrent.{ExecutionContext, Future}
import scala.jdk.CollectionConverters.*

/**
 * Reads the analytics event log back through Amazon Athena over the
 * Glue-cataloged Iceberg table. This is the cloud "serving" transport for the
 * lakehouse: the dashboard summary (and every other analytics response) is
 * derived from rows Athena returns, then passed through the shared
 * [[com.otterworks.analytics.repository.MetricsAggregator]] — so semantics and
 * response schemas are identical to the durable PostgreSQL store and the local
 * Iceberg scan.
 *
 * Enabled by `analytics.iceberg.athena.enabled`; otherwise the repository reads
 * via a direct Iceberg table scan (no AWS required).
 */
class AthenaEventReader(
    aws: AwsConfig,
    iceberg: IcebergConfig
)(using ec: ExecutionContext):

  private val logger = LoggerFactory.getLogger(getClass)

  private lazy val client: AthenaClient =
    val builder = AthenaClient.builder().region(Region.of(aws.region))
      .credentialsProvider(DefaultCredentialsProvider.create())
    aws.endpointUrl.foreach(url => builder.endpointOverride(URI.create(url)))
    builder.build()

  private def fromEpochNanos(n: Long): Instant = Instant.ofEpochSecond(n / 1000000000L, n % 1000000000L)

  private val query: String =
    s"""SELECT seq, event_id, event_type, user_id, resource_id, resource_type,
       |       CAST(metadata AS JSON) AS metadata_json, occurred_at
       |FROM "${iceberg.athena.database}"."${iceberg.table}"
       |ORDER BY seq""".stripMargin

  def loadAll(): Future[Seq[AnalyticsEvent]] = Future {
    val startResp = client.startQueryExecution(
      StartQueryExecutionRequest.builder()
        .queryString(query)
        .queryExecutionContext(QueryExecutionContext.builder().database(iceberg.athena.database).build())
        .workGroup(iceberg.athena.workgroup)
        .resultConfiguration(ResultConfiguration.builder().outputLocation(iceberg.athena.outputLocation).build())
        .build()
    )
    val queryId = startResp.queryExecutionId()
    awaitCompletion(queryId)
    collectRows(queryId)
  }

  @tailrec
  private def awaitCompletion(queryId: String): Unit =
    val exec = client.getQueryExecution(
      GetQueryExecutionRequest.builder().queryExecutionId(queryId).build()
    ).queryExecution()
    exec.status().state() match
      case QueryExecutionState.SUCCEEDED => ()
      case QueryExecutionState.FAILED | QueryExecutionState.CANCELLED =>
        val reason = Option(exec.status().stateChangeReason()).getOrElse("unknown")
        throw new RuntimeException(s"Athena query $queryId did not succeed: $reason")
      case _ =>
        Thread.sleep(500L)
        awaitCompletion(queryId)

  private def collectRows(queryId: String): Seq[AnalyticsEvent] =
    val buffer = scala.collection.mutable.ArrayBuffer.empty[AnalyticsEvent]
    var token: Option[String] = None
    var first = true
    var more = true
    while more do
      val reqBuilder = GetQueryResultsRequest.builder().queryExecutionId(queryId).maxResults(1000)
      token.foreach(reqBuilder.nextToken)
      val resp = client.getQueryResults(reqBuilder.build())
      val rows = resp.resultSet().rows().asScala.toList
      // The very first page includes a header row (column names) to skip.
      val dataRows = if first then rows.drop(1) else rows
      first = false
      dataRows.foreach(row => buffer += toEvent(row.data().asScala.toList))
      token = Option(resp.nextToken())
      more = token.isDefined
    buffer.toVector

  private def cell(cells: List[Datum], idx: Int): String =
    Option(cells(idx).varCharValue()).getOrElse("")

  private def toEvent(cells: List[Datum]): AnalyticsEvent =
    val metadata =
      val raw = cell(cells, 6)
      if raw.isEmpty then Map.empty[String, String]
      else raw.parseJson.convertTo[Map[String, String]]
    AnalyticsEvent(
      eventId = cell(cells, 1),
      eventType = cell(cells, 2),
      userId = cell(cells, 3),
      resourceId = cell(cells, 4),
      resourceType = cell(cells, 5),
      metadata = metadata,
      timestamp = fromEpochNanos(cell(cells, 7).toLong)
    )
