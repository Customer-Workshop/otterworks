package com.otterworks.analytics.reconciliation

import com.otterworks.analytics.repository.MetricsRepository

import scala.concurrent.{ExecutionContext, Future}

final case class ReconciliationCheck(name: String, matches: Boolean, before: String, after: String)

final case class ReconciliationReport(checks: Seq[ReconciliationCheck]):
  def isMatch: Boolean = checks.forall(_.matches)
  def divergences: Seq[ReconciliationCheck] = checks.filterNot(_.matches)

/** Field-level continuous validation across the complete analytics repository contract. */
object AnalyticsReconciler:
  private val periods = Seq("7d", "30d", "90d", "daily", "weekly", "monthly")
  private val contentTypes = Seq("documents", "files", "all")

  def compare(
      before: MetricsRepository,
      after: MetricsRepository,
      userIds: Seq[String],
      resourceIds: Seq[String]
  )(using ec: ExecutionContext): Future[ReconciliationReport] =
    val checks =
      periods.flatMap { period =>
        Seq(
          compareValue(s"dashboard/$period", before.getDashboardSummary(period), after.getDashboardSummary(period)),
          compareValue(s"active-users/$period", before.getActiveUsers(period), after.getActiveUsers(period)),
          compareValue(s"export/$period", before.getExportData(period), after.getExportData(period))
        )
      } ++
        contentTypes.map(t =>
          compareValue(s"top-content/$t", before.getTopContent(t, "30d", 100), after.getTopContent(t, "30d", 100))
        ) ++
        userIds.map(id =>
          compareValue(s"user-activity/$id", before.getUserActivity(id), after.getUserActivity(id))
        ) ++
        resourceIds.map(id =>
          compareValue(s"document-stats/$id", before.getDocumentStats(id), after.getDocumentStats(id))
        ) ++
        Seq(
          compareValue("storage/all", before.getStorageUsage(None), after.getStorageUsage(None)),
          compareValue("event-count", before.getEventCount, after.getEventCount)
        ) ++
        userIds.map(id =>
          compareValue(s"storage/$id", before.getStorageUsage(Some(id)), after.getStorageUsage(Some(id)))
        )

    Future.sequence(checks).map(ReconciliationReport.apply)

  private def compareValue[A](name: String, before: Future[A], after: Future[A])(using
      ec: ExecutionContext
  ): Future[ReconciliationCheck] =
    before.zip(after).map { case (oldValue, newValue) =>
      ReconciliationCheck(name, oldValue == newValue, oldValue.toString, newValue.toString)
    }
