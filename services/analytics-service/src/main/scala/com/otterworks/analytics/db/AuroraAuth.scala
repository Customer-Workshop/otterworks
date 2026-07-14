package com.otterworks.analytics.db

import com.otterworks.analytics.config.PostgresConfig
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.rds.RdsUtilities

import java.io.PrintWriter
import java.net.URI
import java.sql.{Connection, DriverManager}
import java.util.Properties
import java.util.logging.Logger
import javax.sql.DataSource

/**
 * Helpers for connecting the analytics service to Amazon Aurora using IAM
 * database authentication and TLS. This is additive: it is only used when
 * `postgres.iam-auth-enabled` is true. The RDS/static-password path is
 * untouched (see [[AnalyticsDb]]), so a revert is a config flip.
 */
object AuroraAuth:

  /** Host/port parsed from a `jdbc:postgresql://host:port/db` URL. */
  private final case class Endpoint(host: String, port: Int)

  private def parseEndpoint(jdbcUrl: String): Endpoint =
    val authority = URI.create(jdbcUrl.stripPrefix("jdbc:")).getAuthority
    val hostPort = Option(authority).getOrElse("localhost:5432")
    hostPort.split(":", 2) match
      case Array(h, p) => Endpoint(h, p.takeWhile(_.isDigit).toInt)
      case Array(h)    => Endpoint(h, 5432)
      case _           => Endpoint("localhost", 5432)

  /** Append TLS parameters (ssl / sslmode / sslrootcert) to the JDBC URL. */
  def sslJdbcUrl(config: PostgresConfig): String =
    val mode = config.sslMode.trim
    if mode.isEmpty || mode.equalsIgnoreCase("disable") then config.url
    else
      val sep = if config.url.contains("?") then "&" else "?"
      val root =
        if config.sslRootCert.nonEmpty then s"&sslrootcert=${config.sslRootCert}" else ""
      s"${config.url}${sep}ssl=true&sslmode=$mode$root"

  /** Generate a short-lived (~15 min) RDS IAM auth token for the endpoint. */
  def authToken(config: PostgresConfig): String =
    val ep = parseEndpoint(config.url)
    val utilities = RdsUtilities
      .builder()
      .credentialsProvider(DefaultCredentialsProvider.create())
      .region(Region.of(config.iamRegion))
      .build()
    utilities.generateAuthenticationToken(builder =>
      builder
        .hostname(ep.host)
        .port(ep.port)
        .username(config.user)
        .build()
    )

/**
 * A minimal [[javax.sql.DataSource]] that mints a fresh IAM auth token for
 * every physical connection, so tokens never outlive their ~15 minute
 * validity window. TLS parameters are baked into the JDBC URL.
 */
final class IamAuthDataSource(config: PostgresConfig) extends DataSource:
  private val jdbcUrl = AuroraAuth.sslJdbcUrl(config)

  override def getConnection: Connection =
    val props = new Properties()
    props.setProperty("user", config.user)
    props.setProperty("password", AuroraAuth.authToken(config))
    DriverManager.getConnection(jdbcUrl, props)

  override def getConnection(username: String, password: String): Connection = getConnection

  override def getLogWriter: PrintWriter = DriverManager.getLogWriter
  override def setLogWriter(out: PrintWriter): Unit = DriverManager.setLogWriter(out)
  override def setLoginTimeout(seconds: Int): Unit = DriverManager.setLoginTimeout(seconds)
  override def getLoginTimeout: Int = DriverManager.getLoginTimeout
  override def getParentLogger: Logger = Logger.getLogger("com.otterworks.analytics.db")
  override def unwrap[T](iface: Class[T]): T =
    if iface.isInstance(this) then this.asInstanceOf[T]
    else throw new java.sql.SQLException(s"Cannot unwrap to ${iface.getName}")
  override def isWrapperFor(iface: Class[?]): Boolean = iface.isInstance(this)
