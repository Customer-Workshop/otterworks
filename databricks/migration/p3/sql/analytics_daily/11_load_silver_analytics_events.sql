-- Recompute one day of silver from the durable landing. Atomic and rerunnable: REPLACE
-- WHERE swaps this batch's day in one commit, so a rerun of the whole job is a no-op on
-- the same input rather than a double count.
--
-- Scope reproduces the legacy extract exactly (C-2.2): every SQS record is taken whatever
-- date it carries, because the legacy drains the queue and never filters it, while
-- DynamoDB records are taken only when their own `event_date` starts with the run date,
-- because the scan filter is `begins_with(event_date, :ds)`.
--
-- get_json_object, not the `:` operator: field extraction here must be case sensitive.
-- The estate has attribute pairs that differ only in case (the audit table's `Timestamp`
-- against `timestamp`), and a case-insensitive read would quietly repair record shapes the
-- legacy could not read.
INSERT INTO ow_tp.silver.analytics_events_daily
REPLACE WHERE summary_date = CAST(:run_date AS DATE) AND snapshot_batch = :batch
SELECT
  event_uid,
  CAST(:run_date AS DATE) AS summary_date,
  snapshot_batch,
  source_stream,
  ingest_ordinal,
  get_json_object(payload, '$.eventType') AS event_type,
  -- The legacy walks the five fields in order and overwrites while the running value is
  -- still the literal 'unknown', so a field whose value *is* 'unknown' does not stop the
  -- walk. nullif on 'unknown' reproduces that; the default is 'unknown' either way.
  coalesce(
    nullif(nullif(get_json_object(payload, '$.ownerId'), ''), 'unknown'),
    nullif(nullif(get_json_object(payload, '$.editedBy'), ''), 'unknown'),
    nullif(nullif(get_json_object(payload, '$.authorId'), ''), 'unknown'),
    nullif(nullif(get_json_object(payload, '$.deletedBy'), ''), 'unknown'),
    nullif(nullif(get_json_object(payload, '$.userId'), ''), 'unknown'),
    'unknown') AS resolved_user_id,
  CASE
    WHEN try_to_timestamp(replace(get_json_object(payload, '$.timestamp'), 'Z', '+00:00')) IS NULL
      THEN '00'
    -- The hour as written: datetime.fromisoformat keeps the wall-clock hour of the string
    -- and the legacy never converts a timezone, so reading the text is more faithful than
    -- casting to a timestamp and formatting it in the session zone.
    ELSE coalesce(
      nullif(regexp_extract(get_json_object(payload, '$.timestamp'), '[T ]([0-9]{2}):', 1), ''),
      '00')
  END AS event_hour,
  get_json_object(payload, '$.documentId') AS document_id,
  get_json_object(payload, '$.fileId') AS file_id,
  try_cast(get_json_object(payload, '$.sizeBytes') AS BIGINT) AS size_bytes
FROM ow_tp.bronze.analytics_events_raw
WHERE snapshot_batch = :batch
  AND (source_stream = 'sqs' OR startswith(event_date, :run_date))
