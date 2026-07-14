package com.otterworks.analytics.config

import com.typesafe.config.{Config, ConfigFactory}

/** Typed configuration wrapper for the analytics service. */
final case class AppConfig(
    s3: S3Config,
    sqs: SqsConfig,
    aws: AwsConfig,
    postgres: PostgresConfig,
    iceberg: IcebergConfig,
    repository: RepositoryConfig,
    server: ServerConfig
)

final case class S3Config(dataLakeBucket: String)
final case class SqsConfig(eventsQueueUrl: String)
final case class AwsConfig(region: String, endpointUrl: Option[String])
final case class PostgresConfig(
    url: String,
    user: String,
    password: String,
    maxPoolSize: Int
)

/**
 * Configuration for the S3 + Apache Iceberg lakehouse backend (the RE-ARCHITECT
 * "after"). `warehouse` is the Iceberg warehouse root (a `file://` path locally
 * / for the reconciliation harness, or `s3://<data-lake-bucket>/...` in the
 * cloud); `catalog` selects the Iceberg catalog implementation ("hadoop" for the
 * local file warehouse, "glue" for the AWS Glue Data Catalog). Events land in
 * the `<database>.<table>` Iceberg table; the dashboard summary reads back via
 * Amazon Athena when `athena.enabled` is set, otherwise via a direct Iceberg
 * table scan (both derive from the identical Iceberg data).
 */
final case class IcebergConfig(
    warehouse: String,
    catalog: String,
    database: String,
    table: String,
    athena: AthenaConfig
):
  def isGlueCatalog: Boolean = catalog.trim.toLowerCase == "glue"

final case class AthenaConfig(
    enabled: Boolean,
    workgroup: String,
    outputLocation: String,
    database: String
)

/** Selects the metrics store backend: "postgres" (durable, golden default), "iceberg" (S3 lakehouse) or "in-memory". */
final case class RepositoryConfig(backend: String):
  private def normalized: String = backend.trim.toLowerCase
  def isPostgres: Boolean = normalized == "postgres"
  def isIceberg: Boolean = normalized == "iceberg"

final case class ServerConfig(host: String, port: Int)

object AppConfig:
  def load(): AppConfig =
    val config = ConfigFactory.load()
    fromConfig(config)

  def fromConfig(config: Config): AppConfig =
    val analytics = config.getConfig("analytics")

    val s3 = S3Config(
      dataLakeBucket = analytics.getString("s3.data-lake-bucket")
    )

    val sqs = SqsConfig(
      eventsQueueUrl = analytics.getString("sqs.events-queue-url")
    )

    val aws = AwsConfig(
      region = analytics.getString("aws.region"),
      endpointUrl =
        if analytics.hasPath("aws.endpoint-url") then Some(analytics.getString("aws.endpoint-url"))
        else None
    )

    val pg = analytics.getConfig("postgres")
    val postgres = PostgresConfig(
      url = pg.getString("url"),
      user = pg.getString("user"),
      password = pg.getString("password"),
      maxPoolSize = pg.getInt("max-pool-size")
    )

    def optString(path: String, default: String): String =
      if analytics.hasPath(path) then analytics.getString(path) else default
    def optBool(path: String, default: Boolean): Boolean =
      if analytics.hasPath(path) then analytics.getBoolean(path) else default

    val iceberg = IcebergConfig(
      warehouse = optString("iceberg.warehouse", s"s3://${s3.dataLakeBucket}/iceberg"),
      catalog = optString("iceberg.catalog", "glue"),
      database = optString("iceberg.database", "otterworks_analytics"),
      table = optString("iceberg.table", "analytics_events"),
      athena = AthenaConfig(
        enabled = optBool("iceberg.athena.enabled", false),
        workgroup = optString("iceberg.athena.workgroup", "primary"),
        outputLocation = optString("iceberg.athena.output-location", s"s3://${s3.dataLakeBucket}/athena-results/"),
        database = optString("iceberg.athena.database", optString("iceberg.database", "otterworks_analytics"))
      )
    )

    val repository = RepositoryConfig(
      backend =
        if analytics.hasPath("repository.backend") then analytics.getString("repository.backend")
        else "postgres"
    )

    val server = ServerConfig(
      host = if analytics.hasPath("server.host") then analytics.getString("server.host") else "0.0.0.0",
      port = if analytics.hasPath("server.port") then analytics.getInt("server.port") else 8088
    )

    AppConfig(s3, sqs, aws, postgres, iceberg, repository, server)
