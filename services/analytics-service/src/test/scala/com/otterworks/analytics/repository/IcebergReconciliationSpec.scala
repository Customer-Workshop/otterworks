package com.otterworks.analytics.repository

import com.dimafeng.testcontainers.PostgreSQLContainer
import com.otterworks.analytics.config.{IcebergConfig, PostgresConfig}
import com.otterworks.analytics.db.AnalyticsDb
import com.otterworks.analytics.iceberg.LocalIcebergEventStore
import com.otterworks.analytics.model.AnalyticsEvent
import com.otterworks.analytics.model.AnalyticsEventJsonProtocol.given
import com.otterworks.analytics.reconciliation.AnalyticsReconciler
import org.scalatest.BeforeAndAfterAll
import org.scalatest.concurrent.ScalaFutures
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import org.scalatest.time.{Millis, Seconds, Span}
import org.testcontainers.utility.DockerImageName
import spray.json.*

import java.nio.file.Files
import java.time.{Duration, Instant}
import scala.concurrent.{Await, ExecutionContext}
import scala.concurrent.duration.*
import scala.io.Source

/** Continuous validation: PostgreSQL "before" vs Iceberg schema/storage "after". */
class IcebergReconciliationSpec
    extends AnyFlatSpec
    with Matchers
    with ScalaFutures
    with BeforeAndAfterAll:

  given PatienceConfig = PatienceConfig(timeout = Span(60, Seconds), interval = Span(100, Millis))
  given ExecutionContext = ExecutionContext.global

  private var container: Option[PostgreSQLContainer] = None
  private var db: Option[AnalyticsDb] = None

  override def beforeAll(): Unit =
    try
      val c = PostgreSQLContainer(dockerImageNameOverride = DockerImageName.parse("postgres:15-alpine"))
      c.start()
      val database = new AnalyticsDb(PostgresConfig(c.jdbcUrl, c.username, c.password, 4))
      database.migrate()
      container = Some(c)
      db = Some(database)
    catch
      case ex: Throwable =>
        info(s"Docker/Postgres unavailable, skipping reconciliation: ${ex.getMessage}")

  override def afterAll(): Unit =
    db.foreach(_.close())
    container.foreach(_.stop())

  private def loadSeed(): List[AnalyticsEvent] =
    val stream = getClass.getResourceAsStream("/seed/usage-events.ndjson")
    val source = Source.fromInputStream(stream)
    val original =
      try source.getLines().filterNot(_.trim.startsWith("#")).filter(_.trim.nonEmpty)
        .map(_.parseJson.convertTo[AnalyticsEvent]).toList
      finally source.close()

    val latest = original.map(_.timestamp).max
    val shiftedLatest = Instant.now().minusSeconds(3600)
    val offset = Duration.between(latest, shiftedLatest)
    original.map(e => e.copy(timestamp = e.timestamp.plus(offset)))

  "IcebergMetricsRepository" should "match PostgreSQL for every aggregate on the seeded corpus" in {
    assume(db.isDefined, "Docker not available")
    val seed = loadSeed()
    val before = new PostgresMetricsRepository(db.get)

    val warehouse = Files.createTempDirectory("analytics-iceberg-ice1-")
    val iceConfig = IcebergConfig(
      mode = "local",
      database = "otterworks_ice1",
      eventsTable = "analytics_events_ice1",
      aggregatesTable = "analytics_daily_metrics_ice1",
      athenaWorkgroup = "unused",
      athenaOutput = "unused",
      warehouse = "unused",
      localWarehouse = warehouse.toString
    )
    val after = new IcebergMetricsRepository(new LocalIcebergEventStore(iceConfig))
    after.initialize().futureValue

    seed.foreach { event =>
      Await.result(before.storeEvent(event), 10.seconds)
      Await.result(after.storeEvent(event), 10.seconds)
    }

    val report = AnalyticsReconciler.compare(
      before,
      after,
      seed.map(_.userId).distinct :+ "user-unknown",
      seed.map(_.resourceId).distinct :+ "resource-unknown"
    ).futureValue

    withClue(report.divergences.mkString("\n")) {
      report.isMatch shouldBe true
    }

    val beforeRollup = before.getDailyMetrics.futureValue
    val afterRollup = after.getDailyMetrics.futureValue
    afterRollup shouldBe beforeRollup
    afterRollup.map(_.eventCount).sum shouldBe seed.size.toLong
  }
