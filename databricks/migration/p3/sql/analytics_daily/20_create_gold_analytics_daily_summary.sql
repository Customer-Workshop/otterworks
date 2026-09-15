CREATE TABLE IF NOT EXISTS ow_tp.gold.analytics_daily_summary (
  summary_date DATE NOT NULL,
  total_events BIGINT NOT NULL,
  active_users BIGINT NOT NULL COMMENT "distinct resolved users excluding the literal 'unknown' (C-2.7)",
  documents_created BIGINT NOT NULL,
  documents_edited BIGINT NOT NULL,
  comments_added BIGINT NOT NULL,
  files_uploaded BIGINT NOT NULL,
  files_shared BIGINT NOT NULL,
  files_deleted BIGINT NOT NULL,
  bytes_uploaded BIGINT NOT NULL COMMENT 'a byte count, compared exact, not at the float tolerance',
  active_documents BIGINT NOT NULL,
  active_files BIGINT NOT NULL
)
USING DELTA
COMMENT 'Daily analytics summary. Replaces the summary.json.gz object analytics_daily.py wrote to the S3 data lake, and the analytics_daily_summary row it upserted into Postgres.'
