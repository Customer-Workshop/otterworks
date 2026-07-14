package com.otterworks.analytics.repository

import com.otterworks.analytics.model.AnalyticsEvent

import scala.concurrent.duration.*
import scala.concurrent.{Await, ExecutionContext, Future}

/**
 * Continuous-validation reconciliation between two metrics stores.
 *
 * Given a seeded event set and two [[MetricsRepository]] implementations (the
 * durable "before" and the migrated "after"), this asserts that every analytics
 * response agrees field-for-field — the same invariant proven by
 * `PostgresMetricsRepositorySpec`, generalised so the S3 + Iceberg lakehouse
 * "after" can be gated against the PostgreSQL / in-memory "before" on the exact
 * event set before the migration is trusted.
 *
 * The comparison covers every method of the repository contract across all
 * query windows, content types, and the users / documents present in the seed,
 * plus a total event-count check. It returns the list of mismatches (empty when
 * the stores are byte-for-byte identical).
 */
object MetricsReconciler:

  private val periods = List("7d", "30d", "90d", "daily", "weekly", "monthly")
  private val contentTypes = List("documents", "files", "all")

  def reconcile(
      before: MetricsRepository,
      after: MetricsRepository,
      events: Seq[AnalyticsEvent],
      timeout: FiniteDuration = 30.seconds
  )(using ec: ExecutionContext): List[String] =
    val mismatches = scala.collection.mutable.ListBuffer.empty[String]

    def check[A](label: String)(b: => Future[A], a: => Future[A]): Unit =
      val expected = Await.result(b, timeout)
      val actual = Await.result(a, timeout)
      if expected != actual then
        mismatches += s"$label mismatch:\n  before=$expected\n  after =$actual"

    for period <- periods do
      check(s"dashboardSummary[$period]")(before.getDashboardSummary(period), after.getDashboardSummary(period))
      check(s"activeUsers[$period]")(before.getActiveUsers(period), after.getActiveUsers(period))
      check(s"exportData[$period]")(before.getExportData(period), after.getExportData(period))

    for ct <- contentTypes do
      check(s"topContent[$ct]")(before.getTopContent(ct, "30d", 10), after.getTopContent(ct, "30d", 10))

    for user <- events.map(_.userId).distinct.sorted do
      check(s"userActivity[$user]")(before.getUserActivity(user), after.getUserActivity(user))

    for resource <- events.map(_.resourceId).distinct.sorted do
      check(s"documentStats[$resource]")(before.getDocumentStats(resource), after.getDocumentStats(resource))

    check("storageUsage[all]")(before.getStorageUsage(None), after.getStorageUsage(None))
    for user <- events.map(_.userId).distinct.sorted do
      check(s"storageUsage[$user]")(before.getStorageUsage(Some(user)), after.getStorageUsage(Some(user)))

    check("eventCount")(before.getEventCount, after.getEventCount)

    mismatches.toList
