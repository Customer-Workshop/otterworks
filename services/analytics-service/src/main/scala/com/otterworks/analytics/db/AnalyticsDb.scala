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

  private val executor =
    AsyncExecutor("analytics-db", numThreads = config.maxPoolSize, queueSize = 1000)

  // Aurora IAM auth + TLS is opt-in. When disabled (default) the durable store
  // connects exactly as before via static password over plain org.postgresql.
  val database: Database =
    if config.iamAuthEnabled then
      logger.info("Analytics DB using Aurora IAM authentication + TLS")
      Database.forDataSource(new IamAuthDataSource(config), Some(config.maxPoolSize), executor)
    else
      Database.forURL(
        url = config.url,
        user = config.user,
        password = config.password,
        driver = "org.postgresql.Driver",
        executor = executor
      )

  /** Apply pending schema migrations from classpath `db/migration`. */
  def migrate(): Unit =
    val flyway =
      if config.iamAuthEnabled then
        Flyway.configure().dataSource(new IamAuthDataSource(config))
      else
        Flyway.configure().dataSource(config.url, config.user, config.password)
    val result = flyway
      .locations("classpath:db/migration")
      .load()
      .migrate()
    logger.info(
      "Analytics schema migrated to version {} ({} migrations applied)",
      Option(result.targetSchemaVersion).getOrElse("current"),
      result.migrationsExecuted
    )

  def close(): Unit = database.close()
