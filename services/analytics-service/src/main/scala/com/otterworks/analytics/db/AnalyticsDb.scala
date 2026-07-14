package com.otterworks.analytics.db

import com.otterworks.analytics.config.PostgresConfig
import org.flywaydb.core.Flyway
import org.slf4j.LoggerFactory
import slick.jdbc.PostgresProfile.api.*

/** A persisted daily aggregate rollup entry. */
final case class DailyMetric(eventDate: String, eventType: String, eventCount: Long)

/**
 * Owns the Slick database handle and applies the analytics schema via Flyway
 * (the same `db/migration` convention used by the JVM services in this repo).
 *
 * Queries use Slick plain SQL rather than the lifted (Table/TableQuery) API:
 * Slick 3.5's `mapTo`/`TableQuery[T]` rely on Scala 2 macros that cannot run
 * under the Scala 3 compiler, whereas plain SQL is macro-free.
 */
class AnalyticsDb(config: PostgresConfig):
  private val logger = LoggerFactory.getLogger(getClass)

  val database: Database = Database.forURL(
    url = config.url,
    user = config.user,
    password = config.password,
    driver = "org.postgresql.Driver",
    executor = AsyncExecutor("analytics-db", numThreads = config.maxPoolSize, queueSize = 1000)
  )

  /** Apply pending schema migrations from classpath `db/migration`.
   *
   * `connectRetries` lets the initial connection survive an Aurora Serverless v2
   * resume-from-zero; with the default of 0 this is identical to the RDS
   * before-state behavior.
   */
  def migrate(): Unit =
    val result = Flyway
      .configure()
      .dataSource(config.url, config.user, config.password)
      .locations("classpath:db/migration")
      .connectRetries(config.connectRetries)
      .connectRetriesInterval(config.connectRetriesInterval)
      .load()
      .migrate()
    logger.info(
      "Analytics schema migrated to version {} ({} migrations applied)",
      Option(result.targetSchemaVersion).getOrElse("current"),
      result.migrationsExecuted
    )

  def close(): Unit = database.close()
