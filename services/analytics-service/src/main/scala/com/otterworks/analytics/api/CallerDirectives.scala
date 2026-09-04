package com.otterworks.analytics.api

import akka.http.scaladsl.model.StatusCodes
import akka.http.scaladsl.server.Directives.*
import akka.http.scaladsl.server.{Directive1, StandardRoute}

/**
 * Caller identity for user-scoped routes.
 *
 * The api-gateway validates the caller's JWT and injects the authenticated user
 * id as `X-User-ID`; this service treats that header as the only identity. A
 * user-scoped route without the header is unauthenticated (401), and a caller
 * acting on another user's data is forbidden (403).
 */
object CallerDirectives:

  val CallerIdHeader = "X-User-ID"

  /** The authenticated caller id; rejects with 401 when the header is absent or blank. */
  val callerId: Directive1[String] =
    optionalHeaderValueByName(CallerIdHeader).flatMap {
      case Some(id) if id.trim.nonEmpty => provide(id.trim)
      case _ =>
        StandardRoute.toDirective[Tuple1[String]](
          complete(StatusCodes.Unauthorized, s"missing $CallerIdHeader header"))
    }

  /** The caller id, required to be `subject`; 403 for any other authenticated caller. */
  def callerOwning(subject: String): Directive1[String] =
    callerId.flatMap { caller =>
      if caller == subject then provide(caller)
      else
        StandardRoute.toDirective[Tuple1[String]](
          complete(StatusCodes.Forbidden, "caller does not own this resource"))
    }

  /**
   * The caller id for a route whose subject may be supplied as a parameter:
   * the subject defaults to the caller, and an explicit subject must be the caller.
   */
  def callerSubject(requested: Option[String]): Directive1[String] =
    requested.filter(_.trim.nonEmpty).fold(callerId)(callerOwning)
