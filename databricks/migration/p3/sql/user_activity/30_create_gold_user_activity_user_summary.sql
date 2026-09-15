-- user_summaries in the legacy report: the 30-day per-user rollup, ranked.
--
-- The legacy ships user_list[:500] as user_summaries and user_list[:20] as top_users, so
-- top_users is the first 20 rows of this table by rank and is not a second table.
CREATE TABLE IF NOT EXISTS ow_tp.gold.user_activity_user_summary (
  report_date DATE NOT NULL,
  rank INT NOT NULL COMMENT 'position in the legacy sorted list, 1-based; rank <= 20 is its top_users block',
  user_id STRING NOT NULL COMMENT "carries the literal 'unknown' the analytics job writes for an unattributable event (C-2.7)",
  total_actions BIGINT NOT NULL,
  active_days BIGINT NOT NULL COMMENT 'days in the 30-day window the user appears in at all, counted once per daily record as the legacy counts it'
)
USING DELTA
COMMENT 'user_activity_daily.py user_summaries: per-user totals over the 30-day S3 window, capped at 500 rows as the legacy caps them'
