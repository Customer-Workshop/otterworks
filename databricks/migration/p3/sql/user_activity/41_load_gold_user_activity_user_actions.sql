INSERT INTO ow_tp.gold.user_activity_user_actions
REPLACE WHERE report_date = CAST(:run_date AS DATE)
-- Joins the committed ranking rather than recomputing it, so the ranks here cannot drift
-- from the ranks in gold.user_activity_user_summary, and only the users the legacy ships
-- (rank <= 500) get a breakdown.
SELECT s.report_date,
       s.rank,
       s.user_id,
       a.event_type AS action_type,
       CAST(sum(a.event_count) AS BIGINT) AS action_count
FROM ow_tp.gold.user_activity_user_summary s
JOIN ow_tp.gold.analytics_daily_top_user_actions a
  ON a.user_id = s.user_id
 AND a.summary_date BETWEEN date_sub(CAST(:run_date AS DATE), 29) AND CAST(:run_date AS DATE)
WHERE s.report_date = CAST(:run_date AS DATE)
GROUP BY s.report_date, s.rank, s.user_id, a.event_type
