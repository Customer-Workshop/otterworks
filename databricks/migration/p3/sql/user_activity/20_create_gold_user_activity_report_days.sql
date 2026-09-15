-- The daily_summaries array the legacy embeds in activity_report.json: the rows its
-- Postgres query returned, one row per day of the 31-day window, keyed by the report they
-- belong to. Keeping them as their own table is what makes them reconcilable; inside a
-- JSON blob they would only be comparable as bytes.
CREATE TABLE IF NOT EXISTS ow_tp.gold.user_activity_report_days (
  report_date DATE NOT NULL,
  summary_date DATE NOT NULL COMMENT 'report_date in the legacy row; renamed here because the report itself owns report_date',
  active_users BIGINT NOT NULL,
  active_documents BIGINT NOT NULL,
  active_files BIGINT NOT NULL,
  total_events BIGINT NOT NULL,
  documents_created BIGINT NOT NULL,
  documents_edited BIGINT NOT NULL,
  comments_added BIGINT NOT NULL,
  files_uploaded BIGINT NOT NULL,
  files_shared BIGINT NOT NULL,
  files_deleted BIGINT NOT NULL,
  bytes_uploaded BIGINT NOT NULL
)
USING DELTA
COMMENT 'daily_summaries in user_activity_daily.py activity_report.json, one row per day in the report window'
