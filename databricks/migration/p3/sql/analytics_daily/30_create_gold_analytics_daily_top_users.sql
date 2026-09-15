CREATE TABLE IF NOT EXISTS ow_tp.gold.analytics_daily_top_users (
  summary_date DATE NOT NULL,
  rank INT NOT NULL COMMENT '1..100, the position in the legacy top_users.jsonl.gz file',
  user_id STRING NOT NULL COMMENT "includes the literal 'unknown', which active_users excludes (C-2.7)",
  event_count BIGINT NOT NULL
)
USING DELTA
COMMENT 'Top 100 users by event count. Replaces top_users.jsonl.gz; rank is the file order, which is observable output.'
