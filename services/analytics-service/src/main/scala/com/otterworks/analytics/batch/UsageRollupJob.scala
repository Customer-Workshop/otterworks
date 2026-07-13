package com.otterworks.analytics.batch

import com.otterworks.analytics.model.*
import com.otterworks.analytics.model.UsageRollupJsonProtocol.given
import org.slf4j.LoggerFactory
import spray.json.*

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}
import java.time.Instant

/**
 * Nightly usage-rollup batch job (LEGACY "before" state).
 *
 * This is the scheduled, timer-driven batch process that OtterWorks runs to
 * aggregate the previous day's raw analytics events into per-day usage rollups.
 * It runs as a Kubernetes CronJob (`infrastructure/helm/analytics-service`,
 * `templates/cronjob.yaml`) and can be run locally via `make batch-usage-rollup`
 * or `scripts/run-usage-rollup.sh`.
 *
 * Its shape is deliberately batch, NOT event-driven:
 *   1. Wake up on a fixed schedule (cron).
 *   2. Bulk-load ALL events from the source synchronously (poll-and-process).
 *   3. Aggregate in one pass.
 *   4. Write a single output document.
 *
 * See `docs/BATCH-USAGE-ROLLUP.md` for the batch -> event-driven
 * (EventBridge -> SQS -> Lambda) re-architecture this enables. That target is
 * intentionally NOT implemented here.
 */
object UsageRollupJob:

  private val logger = LoggerFactory.getLogger(getClass)

  /** Default classpath location of the bundled deterministic seed events. */
  val DefaultInput = "/seed/usage-events.ndjson"

  /** Default output file path (relative to the working directory). */
  val DefaultOutput = "rollup-output.json"

  final case class Config(input: String, output: String)

  def loadConfig(): Config =
    Config(
      input = sys.env.getOrElse("ROLLUP_INPUT", DefaultInput),
      output = sys.env.getOrElse("ROLLUP_OUTPUT", DefaultOutput)
    )

  /** Build the report document for a bulk set of events, at a fixed clock. */
  def buildReport(events: Seq[AnalyticsEvent], source: String, now: Instant): UsageRollupReport =
    val rollups = UsageRollupAggregator.rollup(events)
    UsageRollupReport(
      generatedAt = now.toString,
      source = source,
      windowStart = rollups.headOption.map(_.date),
      windowEnd = rollups.lastOption.map(_.date),
      dayCount = rollups.size.toLong,
      totalEvents = rollups.map(_.totalEvents).sum,
      rollups = rollups
    )

  /** Run the batch end-to-end and return the written report. */
  def run(config: Config): UsageRollupReport =
    logger.info("Starting nightly usage-rollup batch job (input={}, output={})", config.input, config.output)

    val events = EventLoader.load(config.input)
    logger.info("Bulk-loaded {} raw analytics events from {}", events.size, config.input)

    val report = buildReport(events, config.input, Instant.now())
    logger.info(
      "Aggregated {} events into {} daily rollups (window {} .. {})",
      report.totalEvents,
      report.dayCount,
      report.windowStart.getOrElse("n/a"),
      report.windowEnd.getOrElse("n/a")
    )

    writeReport(Paths.get(config.output), report)
    logger.info("Wrote usage-rollup report to {}", config.output)
    report

  private def writeReport(path: Path, report: UsageRollupReport): Unit =
    Option(path.getParent).foreach(Files.createDirectories(_))
    val json = report.toJson.prettyPrint
    Files.write(path, json.getBytes(StandardCharsets.UTF_8))

  def main(args: Array[String]): Unit =
    val config = loadConfig()
    try
      val report = run(config)
      // Emit a compact, greppable summary line for CronJob logs.
      logger.info("usage-rollup complete: days={} events={}", report.dayCount, report.totalEvents)
    catch
      case ex: Exception =>
        logger.error("usage-rollup batch job failed: {}", ex.getMessage, ex)
        sys.exit(1)
