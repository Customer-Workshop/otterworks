package com.otterworks.analytics.config

import com.typesafe.config.{Config, ConfigFactory}

/** Typed configuration wrapper for the analytics service. */
final case class AppConfig(
    s3: S3Config,
    sqs: SqsConfig,
    aws: AwsConfig,
    postgres: PostgresConfig,
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
    maxPoolSize: Int,
    iamAuthEnabled: Boolean = false,
    sslMode: String = "",
    sslRootCert: String = "",
    iamRegion: String = "us-east-1"
)

/** Selects the metrics store backend: "postgres" (durable, golden default) or "in-memory". */
final case class RepositoryConfig(backend: String):
  def isPostgres: Boolean = backend.trim.toLowerCase == "postgres"

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
      maxPoolSize = pg.getInt("max-pool-size"),
      iamAuthEnabled =
        if pg.hasPath("iam-auth-enabled") then pg.getBoolean("iam-auth-enabled") else false,
      sslMode = if pg.hasPath("ssl-mode") then pg.getString("ssl-mode") else "",
      sslRootCert = if pg.hasPath("ssl-root-cert") then pg.getString("ssl-root-cert") else "",
      iamRegion = if pg.hasPath("iam-region") then pg.getString("iam-region") else "us-east-1"
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

    AppConfig(s3, sqs, aws, postgres, repository, server)
