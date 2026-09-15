-- The `actions` object inside each top_users.jsonl.gz record, flattened.
--
-- top_users carries two things per user: a total and a per-event-type breakdown. The total
-- lives in ow_tp.gold.analytics_daily_top_users; this table is the breakdown, keyed by the
-- same rank so the two compare against one legacy record. 'NaN' is the legacy's own key for
-- a row with no event type, as in the hourly breakdown.
CREATE TABLE IF NOT EXISTS ow_tp.gold.analytics_daily_top_user_actions (
  summary_date DATE NOT NULL,
  rank INT NOT NULL COMMENT 'the users position in top_users.jsonl.gz, 1-based',
  user_id STRING NOT NULL,
  event_type STRING NOT NULL COMMENT "event type as written, or the literal 'NaN' where the row had none",
  event_count BIGINT NOT NULL,
  action_ordinal INT COMMENT 'position of this key inside the records actions object, 1-based'
)
USING DELTA
COMMENT 'Per-event-type action counts for the users in ow_tp.gold.analytics_daily_top_users.'
