package com.otterworks.analytics.repository.iceberg

import com.otterworks.analytics.config.{AthenaConfig, IcebergConfig, PostgresConfig}
import com.otterworks.analytics.repository.{InMemoryMetricsRepository, MetricsReconciler, ReconciliationSeed}

import org.scalatest.concurrent.ScalaFutures
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import org.scalatest.time.{Millis, Seconds, Span}

import java.nio.file.Files
import scala.concurrent.{Await, ExecutionContext}
import scala.concurrent.duration.*

/**
 * Continuous-validation check for the S3 + Apache Iceberg lakehouse "after".
 *
 * Seeds the deterministic [[ReconciliationSeed]] event set into the Iceberg
 * store (a local `file://` Hadoop catalog — no AWS or Docker required) and the
 * in-memory "before" store, then asserts every analytics response is
 * byte-for-byte identical via [[MetricsReconciler]]. This is the same
 * reconciliation invariant `PostgresMetricsRepositorySpec` proves for the
 * durable PostgreSQL store, now gating the lakehouse migration.
 */
class IcebergMetricsRepositorySpec extends AnyFlatSpec with Matchers with ScalaFutures:

  given PatienceConfig = PatienceConfig(timeout = Span(30, Seconds), interval = Span(100, Millis))
  given ExecutionContext = ExecutionContext.global

  private def newIcebergRepo(): IcebergMetricsRepository =
    val warehouse = Files.createTempDirectory("analytics-iceberg-test").toUri.toString
    val config = IcebergConfig(
      warehouse = warehouse,
      catalog = "hadoop",
      database = "otterworks_analytics",
      table = "analytics_events",
      athena = AthenaConfig(enabled = false, workgroup = "primary", outputLocation = "", database = "otterworks_analytics")
    )
    IcebergMetricsRepository.build(config)

  private def seedInto(repo: com.otterworks.analytics.repository.MetricsRepository): Unit =
    ReconciliationSeed.events.foreach(e => Await.result(repo.storeEvent(e), 10.seconds))

  "IcebergMetricsRepository" should "reconcile all analytics with the in-memory before store" in {
    val iceberg = newIcebergRepo()
    seedInto(iceberg)
    val mem = new InMemoryMetricsRepository(PostgresConfig("", "", "", 1))
    seedInto(mem)

    val mismatches = MetricsReconciler.reconcile(mem, iceberg, ReconciliationSeed.events)
    mismatches shouldBe empty
  }

  it should "match the reference dashboard values exactly" in {
    val iceberg = newIcebergRepo()
    seedInto(iceberg)

    val summary = iceberg.getDashboardSummary("30d").futureValue
    summary.totalEvents shouldBe 12
    summary.dailyActiveUsers shouldBe 3
    summary.documentsCreated shouldBe 2
    summary.filesUploaded shouldBe 1
    summary.collabSessions shouldBe 1
    summary.storageUsedBytes shouldBe 2560 // 2048 + 1024 - 512
  }

  it should "retain events durably across repository instances over the same warehouse" in {
    val warehouse = Files.createTempDirectory("analytics-iceberg-durable").toUri.toString
    val config = IcebergConfig(
      warehouse = warehouse,
      catalog = "hadoop",
      database = "otterworks_analytics",
      table = "analytics_events",
      athena = AthenaConfig(enabled = false, workgroup = "primary", outputLocation = "", database = "otterworks_analytics")
    )
    val repo1 = IcebergMetricsRepository.build(config)
    seedInto(repo1)
    val before = repo1.getEventCount.futureValue

    // A fresh repository over the same warehouse sees the persisted events.
    val repo2 = IcebergMetricsRepository.build(config)
    repo2.getEventCount.futureValue shouldBe before
    repo2.getEventCount.futureValue shouldBe ReconciliationSeed.events.size.toLong
  }
