-- Action counts for the users that made the top-100 cut, joined to their rank so a
-- breakdown can never be attributed to the wrong record.
--
-- action_ordinal is the position the key takes inside the record's `actions` object: the
-- legacy builds that object while walking the day's events in arrival order, so the key
-- that appears first is the one whose event arrived first. `ingest_ordinal` is that
-- arrival order as landing recorded it. The order is shipped output -- the report a day
-- later copies it into `actions_by_type` -- and gold otherwise aggregates it away.
INSERT INTO ow_tp.gold.analytics_daily_top_user_actions
REPLACE WHERE summary_date = CAST(:run_date AS DATE)
SELECT summary_date,
       rank,
       user_id,
       event_type,
       event_count,
       CAST(row_number() OVER (PARTITION BY summary_date, user_id ORDER BY first_ordinal)
            AS INT) AS action_ordinal
FROM (
  SELECT t.summary_date,
         t.rank,
         t.user_id,
         coalesce(e.event_type, 'NaN') AS event_type,
         count(*) AS event_count,
         min(e.ingest_ordinal) AS first_ordinal
  FROM ow_tp.gold.analytics_daily_top_users t
  JOIN ow_tp.silver.analytics_events_daily e
    ON e.summary_date = t.summary_date
   AND e.resolved_user_id = t.user_id
  WHERE t.summary_date = CAST(:run_date AS DATE) AND e.snapshot_batch = :batch
  GROUP BY t.summary_date, t.rank, t.user_id, coalesce(e.event_type, 'NaN')
)
