package com.otterworks.analytics.batch

import com.otterworks.analytics.model.*
import com.otterworks.analytics.model.UsageRollupJsonProtocol.given
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import spray.json.*

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path}
import java.time.Instant

class UsageRollupJobSpec extends AnyFlatSpec with Matchers:

  "EventLoader" should "load the bundled deterministic seed resource" in {
    val events = EventLoader.fromResource(UsageRollupJob.DefaultInput)
    events should have size 165
    events.map(_.timestamp).map(_.toString.take(10)).distinct.sorted shouldBe
      List("2024-03-01", "2024-03-02", "2024-03-03")
  }

  it should "ignore comment and blank lines" in {
    val ndjson =
      """# a comment
        |
        |{"eventId":"e1","eventType":"document.created","userId":"u1","resourceId":"d1","resourceType":"document","metadata":{},"timestamp":"2024-03-01T00:00:00Z"}
        |""".stripMargin
    EventLoader.fromString(ndjson) should have size 1
  }

  "UsageRollupJob" should "roll the seed events into three deterministic daily summaries" in {
    val events = EventLoader.fromResource(UsageRollupJob.DefaultInput)
    val report = UsageRollupJob.buildReport(events, UsageRollupJob.DefaultInput, Instant.parse("2024-03-04T02:00:00Z"))

    report.dayCount shouldBe 3L
    report.totalEvents shouldBe 165L
    report.windowStart shouldBe Some("2024-03-01")
    report.windowEnd shouldBe Some("2024-03-03")

    val day = report.rollups.head
    day.date shouldBe "2024-03-01"
    day.totalEvents shouldBe 55L
    day.activeUsers shouldBe 8L
    day.documentsCreated shouldBe 4L
    day.documentsViewed shouldBe 9L
    day.documentsEdited shouldBe 5L
    day.filesUploaded shouldBe 6L
    day.filesDownloaded shouldBe 7L
    day.collabSessions shouldBe 3L
    day.storageAllocatedBytes shouldBe 6L * 1024 * 1024
    day.storageReleasedBytes shouldBe 2L * 1024 * 1024
    day.netStorageBytes shouldBe 4L * 1024 * 1024
  }

  it should "be deterministic across runs on the same input" in {
    val events = EventLoader.fromResource(UsageRollupJob.DefaultInput)
    val a = UsageRollupJob.buildReport(events, "seed", Instant.parse("2024-03-04T00:00:00Z"))
    val b = UsageRollupJob.buildReport(events, "seed", Instant.parse("2024-03-04T00:00:00Z"))
    a.rollups shouldBe b.rollups
  }

  it should "write a valid JSON report to the configured output path" in {
    val tmp: Path = Files.createTempFile("usage-rollup-test", ".json")
    try
      val report = UsageRollupJob.run(UsageRollupJob.Config(UsageRollupJob.DefaultInput, tmp.toString))
      val written = new String(Files.readAllBytes(tmp), StandardCharsets.UTF_8)
      val parsed = written.parseJson.convertTo[UsageRollupReport]
      parsed.rollups shouldBe report.rollups
      parsed.dayCount shouldBe 3L
    finally Files.deleteIfExists(tmp): Unit
  }
