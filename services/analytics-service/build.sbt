val scala3Version = "3.4.0"

lazy val root = project
  .in(file("."))
  .settings(
    name := "analytics-service",
    version := "0.1.0",
    scalaVersion := scala3Version,
    libraryDependencies ++= Seq(
      // Akka HTTP
      "com.typesafe.akka" %% "akka-http" % "10.6.1" cross CrossVersion.for3Use2_13,
      "com.typesafe.akka" %% "akka-actor-typed" % "2.9.1" cross CrossVersion.for3Use2_13,
      "com.typesafe.akka" %% "akka-stream" % "2.9.1" cross CrossVersion.for3Use2_13,
      "com.typesafe.akka" %% "akka-http-spray-json" % "10.6.1" cross CrossVersion.for3Use2_13,

      // JSON
      "io.circe" %% "circe-core" % "0.14.6",
      "io.circe" %% "circe-generic" % "0.14.6",
      "io.circe" %% "circe-parser" % "0.14.6",

      // AWS SDK
      "software.amazon.awssdk" % "s3" % "2.25.6",
      "software.amazon.awssdk" % "sqs" % "2.25.6",

      // Logging
      "ch.qos.logback" % "logback-classic" % "1.5.3",
      "com.typesafe.scala-logging" %% "scala-logging" % "3.9.5" cross CrossVersion.for3Use2_13,

      // Metrics
      "io.prometheus" % "simpleclient" % "0.16.0",
      "io.prometheus" % "simpleclient_httpserver" % "0.16.0",

      // Testing
      "org.scalatest" %% "scalatest" % "3.2.18" % Test,
      "com.typesafe.akka" %% "akka-http-testkit" % "10.6.1" % Test cross CrossVersion.for3Use2_13,
      "com.typesafe.akka" %% "akka-stream-testkit" % "2.9.1" % Test cross CrossVersion.for3Use2_13,
    ),
    assembly / assemblyMergeStrategy := {
      case PathList("META-INF", _*) => MergeStrategy.discard
      case "reference.conf" => MergeStrategy.concat
      case _ => MergeStrategy.first
    },
  )
