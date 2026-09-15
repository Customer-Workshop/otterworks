-- One row per hour and event type. An hour with no events has no row, as the legacy dict
-- has no key for it; a row with an absent or unparseable timestamp counts into '00' rather
-- than being dropped, and a row the legacy could not type counts under 'NaN', because the
-- breakdown is over every row in the frame.
INSERT INTO ow_tp.gold.analytics_daily_hourly
REPLACE WHERE summary_date = CAST(:run_date AS DATE)
SELECT summary_date,
       event_hour AS hour,
       coalesce(event_type, 'NaN') AS event_type,
       count(*) AS event_count
FROM ow_tp.silver.analytics_events_daily
WHERE summary_date = CAST(:run_date AS DATE) AND snapshot_batch = :batch
GROUP BY summary_date, event_hour, coalesce(event_type, 'NaN')
