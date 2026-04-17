package com.otterworks.analytics.model

import spray.json.*
import java.time.Instant
import java.util.UUID

/** Raw analytics event ingested from SQS or the REST API. */
final case class AnalyticsEvent(
    eventId: String,
    eventType: String,
    userId: String,
    resourceId: String,
    resourceType: String,
    metadata: Map[String, String],
    timestamp: Instant
)

object AnalyticsEvent:
  def create(
      eventType: String,
      userId: String,
      resourceId: String,
      resourceType: String,
      metadata: Map[String, String] = Map.empty
  ): AnalyticsEvent =
    AnalyticsEvent(
      eventId = UUID.randomUUID().toString,
      eventType = eventType,
      userId = userId,
      resourceId = resourceId,
      resourceType = resourceType,
      metadata = metadata,
      timestamp = Instant.now()
    )

/** Supported event types across the OtterWorks platform. */
object EventType:
  val DocumentCreated = "document.created"
  val DocumentViewed = "document.viewed"
  val DocumentEdited = "document.edited"
  val DocumentShared = "document.shared"
  val DocumentDeleted = "document.deleted"
  val FileUploaded = "file.uploaded"
  val FileDownloaded = "file.downloaded"
  val FileDeleted = "file.deleted"
  val FileShared = "file.shared"
  val UserLoggedIn = "user.logged_in"
  val UserLoggedOut = "user.logged_out"
  val CollabSessionStarted = "collab.session_started"
  val CollabSessionEnded = "collab.session_ended"
  val StorageAllocated = "storage.allocated"
  val StorageReleased = "storage.released"

  val All: Set[String] = Set(
    DocumentCreated, DocumentViewed, DocumentEdited, DocumentShared, DocumentDeleted,
    FileUploaded, FileDownloaded, FileDeleted, FileShared,
    UserLoggedIn, UserLoggedOut,
    CollabSessionStarted, CollabSessionEnded,
    StorageAllocated, StorageReleased
  )

/** Spray JSON formats for AnalyticsEvent serialization. */
object AnalyticsEventJsonProtocol extends DefaultJsonProtocol:

  given instantFormat: JsonFormat[Instant] = new JsonFormat[Instant]:
    def write(instant: Instant): JsValue = JsString(instant.toString)
    def read(json: JsValue): Instant = json match
      case JsString(s) => Instant.parse(s)
      case JsNumber(n) => Instant.ofEpochMilli(n.toLong)
      case other        => deserializationError(s"Expected ISO-8601 string or epoch millis, got $other")

  given analyticsEventFormat: RootJsonFormat[AnalyticsEvent] =
    jsonFormat7(AnalyticsEvent.apply)

  /** Request payload for POST /api/v1/analytics/events */
  final case class TrackEventRequest(
      eventType: String,
      userId: String,
      resourceId: String,
      resourceType: String,
      metadata: Option[Map[String, String]]
  )

  given trackEventRequestFormat: RootJsonFormat[TrackEventRequest] =
    jsonFormat5(TrackEventRequest.apply)

  /** Standard accepted response. */
  final case class AcceptedResponse(status: String, eventId: String)
  given acceptedResponseFormat: RootJsonFormat[AcceptedResponse] =
    jsonFormat2(AcceptedResponse.apply)
