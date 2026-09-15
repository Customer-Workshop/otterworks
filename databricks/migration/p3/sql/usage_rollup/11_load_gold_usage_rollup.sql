-- The whole of UsageRollupAggregator.rollup as one group-by. Nothing in it needs the JVM.
--
-- Three details are the aggregator's, not this query's, and are copied deliberately:
--
--   * the day is the UTC calendar day of the instant. It is computed from epoch seconds
--     rather than with to_date(), which would resolve the timestamp in the session time
--     zone and silently move events across midnight on a warehouse that is not UTC;
--   * an event type is matched as the exact dotted literal the analytics-service emits.
--     This unit does NOT share analytics_daily's snake_case vocabulary (F-0.9);
--   * metadata['bytes'] is read with `Try(_.toLong).getOrElse(0L)`, so a missing,
--     empty or non-numeric value contributes zero for that one event and does not
--     disturb the rest of the day. The RLIKE is Scala's String.toLong grammar (optional
--     sign, digits, no surrounding space): try_cast alone would accept ' 12 ', which
--     the legacy counts as zero.
--
-- REPLACE WHERE makes a rerun of the same batch a full recompute of exactly the rows it
-- owns, which is what makes the job idempotent.
INSERT INTO ow_tp.gold.usage_rollup
REPLACE WHERE snapshot_batch = :batch
SELECT
  ev.snapshot_batch,
  date_add(DATE'1970-01-01', CAST(floor(unix_timestamp(to_timestamp(ev.event_ts)) / 86400) AS INT)) AS date,
  count(*) AS total_events,
  count(DISTINCT ev.user_id) AS active_users,
  count_if(ev.event_type = 'document.created') AS documents_created,
  count_if(ev.event_type = 'document.viewed') AS documents_viewed,
  count_if(ev.event_type = 'document.edited') AS documents_edited,
  count_if(ev.event_type = 'file.uploaded') AS files_uploaded,
  count_if(ev.event_type = 'file.downloaded') AS files_downloaded,
  count_if(ev.event_type = 'collab.session_started') AS collab_sessions,
  sum(CASE WHEN ev.event_type = 'storage.allocated'
             AND ev.bytes_attr RLIKE '^[+-]?[0-9]+$'
           THEN coalesce(try_cast(ev.bytes_attr AS BIGINT), 0) ELSE 0 END) AS storage_allocated_bytes,
  sum(CASE WHEN ev.event_type = 'storage.released'
             AND ev.bytes_attr RLIKE '^[+-]?[0-9]+$'
           THEN coalesce(try_cast(ev.bytes_attr AS BIGINT), 0) ELSE 0 END) AS storage_released_bytes,
  sum(CASE WHEN ev.event_type = 'storage.allocated'
             AND ev.bytes_attr RLIKE '^[+-]?[0-9]+$'
           THEN coalesce(try_cast(ev.bytes_attr AS BIGINT), 0) ELSE 0 END)
  - sum(CASE WHEN ev.event_type = 'storage.released'
               AND ev.bytes_attr RLIKE '^[+-]?[0-9]+$'
             THEN coalesce(try_cast(ev.bytes_attr AS BIGINT), 0) ELSE 0 END) AS net_storage_bytes,
  current_timestamp() AS generated_at
FROM ow_tp.bronze.usage_events_raw AS ev
WHERE ev.snapshot_batch = :batch
GROUP BY
  ev.snapshot_batch,
  date_add(DATE'1970-01-01', CAST(floor(unix_timestamp(to_timestamp(ev.event_ts)) / 86400) AS INT))
