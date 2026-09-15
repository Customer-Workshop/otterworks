-- hourly_breakdown.json.gz, flattened: the legacy file is {hour: {event_type: count}}, so
-- the grain here is (hour, event type), not hour. An hour-total-only table would compare
-- green while the per-type split inside the hour differed.
--
-- event_type carries the legacy's own label for a row with no eventType: pandas leaves the
-- value NaN and json.dumps writes the key as the string "NaN". That literal is output, not
-- an internal detail, so the target reproduces it rather than a NULL that would compare
-- against nothing.
CREATE TABLE IF NOT EXISTS ow_tp.gold.analytics_daily_hourly (
  summary_date DATE NOT NULL,
  hour STRING NOT NULL COMMENT "zero-padded two characters, '00'..'23'; '00' also holds the malformed and absent timestamp fallback (C-2.8)",
  event_type STRING NOT NULL COMMENT "the legacy's key: the event type as written, or the literal 'NaN' where the row had none",
  event_count BIGINT NOT NULL
)
USING DELTA
COMMENT 'Replaces hourly_breakdown.json.gz: one row per hour and event type.'
