-- Top 100 users, in the legacy's file order.
--
-- The legacy builds a dict keyed by user in frame order, then `sort(key=total,
-- reverse=True)`. Python's sort is stable and reverse=True does not reverse equal
-- elements, so users on the same total keep the order in which they first appeared in
-- `sqs_events + dynamo_events`. That order is reproduced here from ingest_ordinal, which
-- landing recorded; it is not an invented tie-break, and 'unknown' is a user here even
-- though active_users excludes it.
INSERT INTO ow_tp.gold.analytics_daily_top_users
REPLACE WHERE summary_date = CAST(:run_date AS DATE)
WITH per_user AS (
  SELECT summary_date,
         resolved_user_id AS user_id,
         count(*) AS event_count,
         min(ingest_ordinal) AS first_seen
  FROM ow_tp.silver.analytics_events_daily
  WHERE summary_date = CAST(:run_date AS DATE) AND snapshot_batch = :batch
  GROUP BY summary_date, resolved_user_id
)
SELECT summary_date,
       CAST(row_number() OVER (PARTITION BY summary_date
                               ORDER BY event_count DESC, first_seen ASC) AS INT) AS rank,
       user_id,
       event_count
FROM per_user
QUALIFY rank <= 100
