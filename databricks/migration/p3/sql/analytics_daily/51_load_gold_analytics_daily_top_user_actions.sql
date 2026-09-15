-- Action counts for the users that made the top-100 cut, joined to their rank so a
-- breakdown can never be attributed to the wrong record.
INSERT INTO ow_tp.gold.analytics_daily_top_user_actions
REPLACE WHERE summary_date = CAST(:run_date AS DATE)
SELECT t.summary_date,
       t.rank,
       t.user_id,
       coalesce(e.event_type, 'NaN') AS event_type,
       count(*) AS event_count
FROM ow_tp.gold.analytics_daily_top_users t
JOIN ow_tp.silver.analytics_events_daily e
  ON e.summary_date = t.summary_date
 AND e.resolved_user_id = t.user_id
WHERE t.summary_date = CAST(:run_date AS DATE) AND e.snapshot_batch = :batch
GROUP BY t.summary_date, t.rank, t.user_id, coalesce(e.event_type, 'NaN')
