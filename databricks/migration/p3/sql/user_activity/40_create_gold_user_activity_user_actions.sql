-- actions_by_type inside each user_summaries entry, one row per (user, action type).
--
-- A total alone compares green while the split under it differs, which is the same reason
-- gold.analytics_daily_top_user_actions exists a layer down.
CREATE TABLE IF NOT EXISTS ow_tp.gold.user_activity_user_actions (
  report_date DATE NOT NULL,
  rank INT NOT NULL,
  user_id STRING NOT NULL,
  action_type STRING NOT NULL COMMENT "the legacy's own key, including the literal 'NaN' for an event its frame could not type and the unnormalised dotted 'document.created' (F-0.9)",
  action_count BIGINT NOT NULL
)
USING DELTA
COMMENT 'actions_by_type in user_activity_daily.py user_summaries, summed over the 30-day window'
