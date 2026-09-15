INSERT INTO ow_tp.gold.user_activity_user_actions
REPLACE WHERE report_date = CAST(:run_date AS DATE)
-- Joins the committed ranking rather than recomputing it, so the ranks here cannot drift
-- from the ranks in gold.user_activity_user_summary, and only the users the legacy ships
-- (rank <= 500) get a breakdown.
--
-- action_ordinal is the order the keys take inside the user's `actions_by_type` object.
-- The legacy walks the window newest day first and, inside a day, the record's own
-- `actions` keys in order, adding a key the first time it sees it -- so a key's position
-- is where it first appeared. That is what the struct minimum picks: the smallest
-- (day offset from the run date, position inside that day's record) pair.
--
-- A contributing row whose own ordinal is NULL (a day loaded before the column existed)
-- carries no order, so every key of that user is emitted with a NULL ordinal instead of a
-- row_number() that would look like recovered order. export_user_activity.py refuses to
-- build the report from NULL ordinals, so the run fails loudly rather than shipping keys
-- in an order nothing in the data supports.
SELECT report_date,
       rank,
       user_id,
       action_type,
       action_count,
       CASE WHEN max(order_unknown) OVER (PARTITION BY report_date, user_id) = 1
            THEN CAST(NULL AS INT)
            ELSE CAST(row_number() OVER (PARTITION BY report_date, user_id ORDER BY first_seen)
                      AS INT)
       END AS action_ordinal
FROM (
  SELECT s.report_date,
         s.rank,
         s.user_id,
         a.event_type AS action_type,
         CAST(sum(a.event_count) AS BIGINT) AS action_count,
         max(CASE WHEN a.action_ordinal IS NULL THEN 1 ELSE 0 END) AS order_unknown,
         min(struct(datediff(CAST(:run_date AS DATE), a.summary_date) AS day_offset,
                    a.action_ordinal AS position)) AS first_seen
  FROM ow_tp.gold.user_activity_user_summary s
  JOIN ow_tp.gold.analytics_daily_top_user_actions a
    ON a.user_id = s.user_id
   AND a.summary_date BETWEEN date_sub(CAST(:run_date AS DATE), 29) AND CAST(:run_date AS DATE)
  WHERE s.report_date = CAST(:run_date AS DATE)
  GROUP BY s.report_date, s.rank, s.user_id, a.event_type
)
