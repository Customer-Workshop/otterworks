-- Typed, legacy-faithful view of one analytics day, from the durable bronze landing.
--
-- Every column here is a clause of the record contract (docs/migration/
-- Pipeline3_analytics_record_contract.md §2), not a modelling choice:
--
--   event_type        analytics_daily.py copies `event_type` into `eventType` only when no
--                     record in the batch carries `eventType` (a frame-level test, not a
--                     row-level one). The estate's batches always contain both spellings,
--                     so a record that carries only `event_type` has a NULL event type and
--                     matches none of the `== 'document_created'` comparisons (C-2.4).
--   resolved_user_id  first non-null, non-empty of ownerId, editedBy, authorId, deletedBy,
--                     userId, else the literal 'unknown' (C-2.6).
--   event_hour        two characters. The legacy takes the hour field of the timestamp as
--                     written, with no timezone conversion, and falls back to '00' when the
--                     value is absent, not a string, or unparseable (C-2.8).
CREATE TABLE IF NOT EXISTS ow_tp.silver.analytics_events_daily (
  event_uid STRING NOT NULL,
  summary_date DATE NOT NULL COMMENT 'the run date the legacy job would have been invoked for',
  snapshot_batch STRING NOT NULL,
  source_stream STRING NOT NULL,
  ingest_ordinal BIGINT NOT NULL COMMENT 'legacy concatenation order; ties in top_users resolve on it',
  event_type STRING COMMENT 'NULL where the legacy frame has no eventType value for the row',
  resolved_user_id STRING NOT NULL,
  event_hour STRING NOT NULL COMMENT "'00'..'23'; '00' also absorbs absent and unparseable timestamps",
  document_id STRING,
  file_id STRING,
  size_bytes BIGINT
)
USING DELTA
COMMENT 'analytics_daily.py rows as its pandas frame saw them, one row per event.'
