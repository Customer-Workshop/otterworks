INSERT INTO ow_tp.gold.user_activity_report
REPLACE WHERE report_date = CAST(:run_date AS DATE)
WITH window_days AS (
  -- The legacy's Postgres query is BETWEEN ds - interval '30 days' AND ds, which is 31
  -- days and not 30. The per-user S3 loop below it walks range(30), which is 30. The two
  -- windows really are different widths in the same report, so the target keeps both
  -- rather than tidying them into one.
  SELECT total_events, active_users
  FROM ow_tp.gold.analytics_daily_summary
  WHERE summary_date BETWEEN date_sub(CAST(:run_date AS DATE), 30) AND CAST(:run_date AS DATE)
)
SELECT CAST(:run_date AS DATE) AS report_date,
       CAST(30 AS INT) AS lookback_days,
       CAST(coalesce(sum(total_events), 0) AS BIGINT) AS total_events,
       -- max(...) over an empty window, which the legacy spells max(..., default=0).
       CAST(coalesce(max(active_users), 0) AS BIGINT) AS peak_active_users,
       CAST(CASE WHEN count(*) = 0 THEN 0
                 ELSE bround(sum(total_events) / count(*), 2) END AS DOUBLE) AS avg_daily_events,
       CAST(count(*) AS BIGINT) AS reporting_days
FROM window_days
