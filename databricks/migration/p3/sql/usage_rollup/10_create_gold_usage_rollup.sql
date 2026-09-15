-- P3-D06: UsageRollupJob.scala + UsageRollupAggregator.scala become this table and the
-- query that loads it. The Scala writes one JSON document per run (`DailyUsageRollup`
-- objects inside a `UsageRollupReport`); the durable equivalent is one row per UTC day.
--
-- The report's envelope fields are not columns: generated_at is the wall clock,
-- source/window_start/window_end/day_count/total_events are all derivable from the rows
-- themselves, and storing a run's own summary of its rows invites the two to disagree.
CREATE TABLE IF NOT EXISTS ow_tp.gold.usage_rollup (
  snapshot_batch STRING NOT NULL COMMENT 'input snapshot the rollup was computed from; the legacy has no date parameter at all, its scope is whatever the input file holds',
  date DATE NOT NULL COMMENT 'UTC calendar day of the event timestamp',
  total_events BIGINT NOT NULL COMMENT 'every event of the day, including types with no counter of their own',
  active_users BIGINT NOT NULL COMMENT 'distinct userId; unattributed values are counted as themselves, not dropped',
  documents_created BIGINT NOT NULL,
  documents_viewed BIGINT NOT NULL,
  documents_edited BIGINT NOT NULL,
  files_uploaded BIGINT NOT NULL,
  files_downloaded BIGINT NOT NULL,
  collab_sessions BIGINT NOT NULL COMMENT 'collab.session_started only; session_ended is not counted',
  storage_allocated_bytes BIGINT NOT NULL,
  storage_released_bytes BIGINT NOT NULL,
  net_storage_bytes BIGINT NOT NULL COMMENT 'allocated minus released; signed, legitimately negative on a day that released more than it allocated',
  generated_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Daily usage rollup, the Delta equivalent of UsageRollupJob.scala. F-0.6: the estate CronJob writes its report to an emptyDir destroyed on pod exit, so nothing in this repo consumes the legacy output; whether a consumer exists in production is a STOP E question.'
