package com.otterworks.analytics.service

import akka.actor.typed.ActorSystem
import akka.stream.scaladsl.{Sink, Source}
import com.otterworks.analytics.api.Metrics
import com.otterworks.analytics.config.{AppConfig, SqsConfig}
import net.logstash.logback.argument.StructuredArguments.kv
import org.slf4j.LoggerFactory
import io.circe.parser.decode
import io.circe.generic.auto.*
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.sqs.SqsClient
import software.amazon.awssdk.services.sqs.model.{DeleteMessageRequest, ReceiveMessageRequest}

import java.net.URI
import scala.concurrent.{ExecutionContext, Future}
import scala.concurrent.duration.*
import scala.jdk.CollectionConverters.*
import scala.util.{Failure, Success, Try}

/**
 * SQS-based event processor that consumes analytics events from a queue
 * and feeds them into the AnalyticsService for processing and storage.
 *
 * Uses Akka Streams for backpressure-aware processing of incoming events.
 */
class EventProcessor(
    config: AppConfig,
    analyticsService: AnalyticsService
)(using system: ActorSystem[?], ec: ExecutionContext):

  private val logger = LoggerFactory.getLogger(getClass)

  /** Queue name (last URL segment) for logs; the full URL carries the account id. */
  private val queueName: String = config.sqs.eventsQueueUrl.split('/').lastOption.getOrElse("unknown")

  private lazy val sqsClient: SqsClient =
    val builder = SqsClient.builder()
      .region(Region.of(config.aws.region))
      .credentialsProvider(DefaultCredentialsProvider.create())
    config.aws.endpointUrl.foreach(url => builder.endpointOverride(URI.create(url)))
    builder.build()

  /** Raw SQS message payload for circe decoding. */
  private case class SqsEventPayload(
      eventType: String,
      userId: String,
      resourceId: String,
      resourceType: String,
      metadata: Option[Map[String, String]]
  )

  /**
   * Start polling SQS for events. This runs as an Akka Stream that
   * periodically receives messages, processes them, and deletes them
   * from the queue.
   */
  def start(): Unit =
    logger.info("sqs_processor_starting", kv("queue", queueName), kv("region", config.aws.region))

    Source
      .tick(1.second, 5.seconds, ())
      .mapAsync(1) { _ =>
        Future {
          Try {
            val request = ReceiveMessageRequest.builder()
              .queueUrl(config.sqs.eventsQueueUrl)
              .maxNumberOfMessages(10)
              .waitTimeSeconds(2)
              .build()
            sqsClient.receiveMessage(request).messages().asScala.toList
          } match
            case Success(msgs) => msgs
            case Failure(ex) =>
              Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.ReceiveFailed).inc()
              logger.warn("sqs_receive_failed", kv("queue", queueName), kv("error", ex.getMessage), ex)
              List.empty
        }
      }
      .mapConcat(identity)
      .mapAsync(4) { message =>
        decode[SqsEventPayload](message.body()) match
          case Right(payload) =>
            analyticsService
              .trackEvent(
                payload.eventType,
                payload.userId,
                payload.resourceId,
                payload.resourceType,
                payload.metadata.getOrElse(Map.empty)
              )
              .map { event =>
                Metrics.eventsReceivedTotal.labels(Metrics.Source.Sqs, event.eventType).inc()
                Try {
                  val deleteReq = DeleteMessageRequest.builder()
                    .queueUrl(config.sqs.eventsQueueUrl)
                    .receiptHandle(message.receiptHandle())
                    .build()
                  sqsClient.deleteMessage(deleteReq)
                } match
                  case Success(_) =>
                    Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.Processed).inc()
                    logger.debug(
                      "sqs_event_processed",
                      kv("queue", queueName),
                      kv("event_id", event.eventId),
                      kv("event_type", event.eventType))
                  case Failure(ex) =>
                    Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.DeleteFailed).inc()
                    logger.error(
                      "sqs_delete_failed",
                      kv("queue", queueName),
                      kv("event_id", event.eventId),
                      kv("error", ex.getMessage),
                      ex)
              }
              .recover { case ex =>
                Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.StoreFailed).inc()
                logger.error(
                  "sqs_event_store_failed",
                  kv("queue", queueName),
                  kv("event_type", payload.eventType),
                  kv("error", ex.getMessage),
                  ex)
              }
          case Left(err) =>
            Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.DecodeFailed).inc()
            logger.error("sqs_decode_failed", kv("queue", queueName), kv("error", err.getMessage))
            Try {
              val deleteReq = DeleteMessageRequest.builder()
                .queueUrl(config.sqs.eventsQueueUrl)
                .receiptHandle(message.receiptHandle())
                .build()
              sqsClient.deleteMessage(deleteReq)
            } match
              case Success(_) =>
                logger.warn("sqs_undecodable_message_deleted", kv("queue", queueName))
              case Failure(ex) =>
                Metrics.sqsMessagesTotal.labels(Metrics.SqsOutcome.DeleteFailed).inc()
                logger.error(
                  "sqs_delete_failed",
                  kv("queue", queueName),
                  kv("error", ex.getMessage),
                  ex)
            Future.successful(())
      }
      .runWith(Sink.ignore)

    logger.info("sqs_processor_started", kv("queue", queueName)): Unit
