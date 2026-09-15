-- The trends block of the legacy's activity_report.json, one row per report date.
--
-- `avg_daily_events` is the only float pipeline 3 ships. The legacy computes it as a
-- Python float division rounded with round(), which is half-to-even, so the target uses
-- bround() and not round(): on a tie (…x.xx5) Spark's round() would go up where Python
-- goes to the even digit, and the two would disagree by 0.01 on exactly the values a
-- reviewer would never think to check.
CREATE TABLE IF NOT EXISTS ow_tp.gold.user_activity_report (
  report_date DATE NOT NULL,
  lookback_days INT NOT NULL,
  total_events BIGINT NOT NULL,
  peak_active_users BIGINT NOT NULL,
  avg_daily_events DOUBLE NOT NULL,
  reporting_days BIGINT NOT NULL
)
USING DELTA
COMMENT 'user_activity_daily.py trends block: 31 days of analytics_daily_summary rolled up for one report date'
