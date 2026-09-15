INSERT INTO ow_tp.gold.user_activity_user_summary
REPLACE WHERE report_date = CAST(:run_date AS DATE)
WITH per_day AS (
  -- The legacy's input is the top_users.jsonl.gz object analytics_daily.py wrote for each
  -- of the 30 days; the target reads the Delta table that object became. A day with no
  -- rows is simply absent on both sides: the legacy swallows the S3 404 and skips it, and
  -- here there is nothing to read. The window is 30 days ending on the report date
  -- (range(30) counting back from the execution date), one narrower than the summary
  -- window in 11_load_gold_user_activity_report.sql.
  SELECT summary_date, rank, user_id, event_count
  FROM ow_tp.gold.analytics_daily_top_users
  WHERE summary_date BETWEEN date_sub(CAST(:run_date AS DATE), 29) AND CAST(:run_date AS DATE)
),
per_user AS (
  SELECT user_id,
         sum(event_count) AS total_actions,
         -- The legacy does active_days += 1 per record it reads, not per distinct date.
         count(*) AS active_days,
         -- Tie-break. The legacy builds user_totals by walking day_offset 0..29 -- newest
         -- day first -- and within a day in file order, then sorts on total_actions with
         -- Python's stable sort, so equal totals keep first-appearance order. That order
         -- is (days back from the report date, then rank within the day); rank is capped
         -- at 100 upstream, so 1000 keeps the two components from colliding.
         min(datediff(CAST(:run_date AS DATE), summary_date) * 1000 + rank) AS first_seen
  FROM per_day
  GROUP BY user_id
),
ranked AS (
  SELECT CAST(:run_date AS DATE) AS report_date,
         CAST(row_number() OVER (ORDER BY total_actions DESC, first_seen ASC) AS INT) AS rank,
         user_id,
         total_actions,
         active_days
  FROM per_user
)
-- The cap is a filter on a subquery rather than QUALIFY: `rank` is also a window function,
-- and per_day carries a column of that name, so a bare `QUALIFY rank <= 500` is asking the
-- analyser to pick between three readings of the same word.
SELECT report_date, rank, user_id, total_actions, active_days
FROM ranked
WHERE rank <= 500
