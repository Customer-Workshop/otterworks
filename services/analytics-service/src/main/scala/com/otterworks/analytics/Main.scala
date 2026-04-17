package com.otterworks.analytics

import akka.actor.typed.ActorSystem
import akka.actor.typed.scaladsl.Behaviors
import akka.http.scaladsl.Http
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.Route
import com.otterworks.analytics.api.{AnalyticsRoutes, HealthRoutes}

import scala.concurrent.ExecutionContextExecutor
import scala.util.{Failure, Success}

object Main:
  def main(args: Array[String]): Unit =
    implicit val system: ActorSystem[Nothing] = ActorSystem(Behaviors.empty, "analytics-service")
    implicit val ec: ExecutionContextExecutor = system.executionContext

    val port = sys.env.getOrElse("PORT", "8088").toInt
    val host = "0.0.0.0"

    val routes: Route = concat(
      HealthRoutes.routes,
      AnalyticsRoutes.routes,
    )

    val binding = Http().newServerAt(host, port).bind(routes)
    binding.onComplete {
      case Success(b) =>
        system.log.info(s"Analytics Service started at http://${b.localAddress.getHostString}:${b.localAddress.getPort}")
      case Failure(e) =>
        system.log.error(s"Failed to start Analytics Service: ${e.getMessage}")
        system.terminate()
    }
