val scala3Version = "3.3.8"

lazy val root = project
  .in(file("."))
  .settings(
    name := "analytics-service",
    version := "0.1.0",
    scalaVersion := scala3Version,
    // The HTTP server is the default entrypoint (`java -jar`). The batch job
    // (com.otterworks.analytics.batch.UsageRollupJob) is a second main class run
    // explicitly via `java -cp app.jar ...` (see the analytics-service CronJob).
    Compile / mainClass := Some("com.otterworks.analytics.Main"),
    assembly / mainClass := Some("com.otterworks.analytics.Main"),
    libraryDependencies ++= Seq(
      // Apache Pekko HTTP
      "org.apache.pekko" %% "pekko-http" % "1.4.0",
      "org.apache.pekko" %% "pekko-actor-typed" % "1.7.0",
      "org.apache.pekko" %% "pekko-stream" % "1.7.0",
      "org.apache.pekko" %% "pekko-http-spray-json" % "1.4.0",

      // JSON
      "io.circe" %% "circe-core" % "0.14.16",
      "io.circe" %% "circe-generic" % "0.14.16",
      "io.circe" %% "circe-parser" % "0.14.16",

      // Database - Slick for PostgreSQL
      "com.typesafe.slick" %% "slick" % "3.6.1" cross CrossVersion.for3Use2_13,
      "com.typesafe.slick" %% "slick-hikaricp" % "3.6.1" cross CrossVersion.for3Use2_13,
      "org.postgresql" % "postgresql" % "42.7.13",

      // Schema migrations (Flyway 10+ provides database support separately)
      "org.flywaydb" % "flyway-core" % "13.3.0",
      "org.flywaydb" % "flyway-database-postgresql" % "13.3.0",

      // AWS SDK
      "software.amazon.awssdk" % "s3" % "2.54.0",
      "software.amazon.awssdk" % "sqs" % "2.54.0",

      // Configuration
      "com.typesafe" % "config" % "1.4.9",

      // Logging
      "ch.qos.logback" % "logback-classic" % "1.5.38",
      "net.logstash.logback" % "logstash-logback-encoder" % "9.0",
      "org.slf4j" % "slf4j-api" % "2.0.18",

      // Metrics
      "io.prometheus" % "prometheus-metrics-core" % "1.8.0",
      "io.prometheus" % "prometheus-metrics-exposition-textformats" % "1.8.0",
      "io.prometheus" % "prometheus-metrics-instrumentation-jvm" % "1.8.0",

      // Testing
      "org.scalatest" %% "scalatest" % "3.2.20" % Test,
      "org.apache.pekko" %% "pekko-http-testkit" % "1.4.0" % Test,
      "org.apache.pekko" %% "pekko-stream-testkit" % "1.7.0" % Test,
      "org.apache.pekko" %% "pekko-actor-testkit-typed" % "1.7.0" % Test,

      // Integration testing against a real PostgreSQL (skipped when Docker is unavailable)
      "com.dimafeng" %% "testcontainers-scala-scalatest" % "0.44.1" % Test,
      "com.dimafeng" %% "testcontainers-scala-postgresql" % "0.44.1" % Test,
    ),
    assembly / assemblyMergeStrategy := {
      // Preserve ServiceLoader registrations (Flyway discovers its database
      // and plugin support via META-INF/services).
      case PathList("META-INF", "services", _*) => MergeStrategy.concat
      case PathList("META-INF", _*) => MergeStrategy.discard
      case "reference.conf" => MergeStrategy.concat
      case _ => MergeStrategy.first
    },
  )
