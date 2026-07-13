package com.otterworks.analytics.batch

import com.otterworks.analytics.model.*
import com.otterworks.analytics.model.AnalyticsEventJsonProtocol.given
import spray.json.*

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}
import scala.jdk.CollectionConverters.*
import scala.util.Using

/**
 * Loads analytics events in bulk from a newline-delimited JSON (NDJSON) source.
 *
 * This is the legacy "poll-and-process" input for the nightly batch job: the
 * whole day's events are read into memory up front, synchronously, then handed
 * to the aggregator. Blank lines and lines beginning with `#` are ignored so the
 * seed file can carry comments.
 */
object EventLoader:

  /** Parse events from an in-memory NDJSON string. */
  def fromString(ndjson: String): List[AnalyticsEvent] =
    ndjson.linesIterator
      .map(_.trim)
      .filter(line => line.nonEmpty && !line.startsWith("#"))
      .map(parseLine)
      .toList

  /** Load events from a file on disk. */
  def fromFile(path: Path): List[AnalyticsEvent] =
    val content = new String(Files.readAllBytes(path), StandardCharsets.UTF_8)
    fromString(content)

  /** Load events from a classpath resource (e.g. the bundled seed file). */
  def fromResource(resourcePath: String): List[AnalyticsEvent] =
    val stream = Option(getClass.getResourceAsStream(resourcePath))
      .getOrElse(throw new IllegalArgumentException(s"Seed resource not found on classpath: $resourcePath"))
    Using.resource(stream) { in =>
      fromString(new String(in.readAllBytes(), StandardCharsets.UTF_8))
    }

  /**
   * Resolve an input reference to events: an existing filesystem path is read as
   * a file, otherwise the reference is treated as a classpath resource.
   */
  def load(inputRef: String): List[AnalyticsEvent] =
    val asPath = Paths.get(inputRef)
    if Files.isRegularFile(asPath) then fromFile(asPath)
    else fromResource(inputRef)

  private def parseLine(line: String): AnalyticsEvent =
    line.parseJson.convertTo[AnalyticsEvent]
