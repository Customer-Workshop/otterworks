package com.otterworks.analytics.batch

import com.otterworks.analytics.config.{AthenaConfig, IcebergConfig}
import com.otterworks.analytics.model.AnalyticsEvent
import com.otterworks.analytics.repository.iceberg.IcebergMetricsRepository
import com.otterworks.analytics.repository.{InMemoryMetricsRepository, MetricsReconciler, MetricsRepository, ReconciliationSeed}
import com.otterworks.analytics.config.PostgresConfig

import java.nio.file.Files
import scala.concurrent.duration.*
import scala.concurrent.{Await, ExecutionContext}

/**
 * Continuous-validation harness for the analytics lakehouse migration.
 *
 * Seeds the deterministic [[ReconciliationSeed]] event set into both the
 * in-memory "before" store (byte-for-byte equivalent to the durable PostgreSQL
 * store — see `PostgresMetricsRepositorySpec`) and the S3 + Iceberg "after"
 * store, then asserts every analytics response agrees. Uses a local `file://`
 * Hadoop-catalog warehouse so it runs with no AWS or Docker — the same check
 * runs against a Glue-cataloged S3 table in the cloud by pointing
 * `ANALYTICS_ICEBERG_*` at it.
 *
 * Exits non-zero on any mismatch so it can gate the migration in CI / a demo.
 *
 * Run: `sbt "runMain com.otterworks.analytics.batch.ReconciliationCheck"`.
 */
object ReconciliationCheck:

  def main(args: Array[String]): Unit =
    given ec: ExecutionContext = ExecutionContext.global

    val warehouse = Files.createTempDirectory("analytics-iceberg-recon").toUri.toString
    val config = IcebergConfig(
      warehouse = warehouse,
      catalog = "hadoop",
      database = "otterworks_analytics",
      table = "analytics_events",
      athena = AthenaConfig(enabled = false, workgroup = "primary", outputLocation = "", database = "otterworks_analytics")
    )

    val before: MetricsRepository = new InMemoryMetricsRepository(PostgresConfig("", "", "", 1))
    val after: MetricsRepository = IcebergMetricsRepository.build(config)

    val events: Seq[AnalyticsEvent] = ReconciliationSeed.events
    events.foreach { e =>
      Await.result(before.storeEvent(e), 10.seconds)
      Await.result(after.storeEvent(e), 10.seconds)
    }

    println(s"[reconcile] seeded ${events.size} events; warehouse=$warehouse")
    val mismatches = MetricsReconciler.reconcile(before, after, events)

    if mismatches.isEmpty then
      println(s"[reconcile] OK — Iceberg lakehouse reconciles with the before store on all ${events.size} seeded events")
      sys.exit(0)
    else
      println(s"[reconcile] FAILED — ${mismatches.size} mismatch(es):")
      mismatches.foreach(m => println(s"  - $m"))
      sys.exit(1)
