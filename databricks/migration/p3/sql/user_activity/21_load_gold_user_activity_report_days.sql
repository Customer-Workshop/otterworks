INSERT INTO ow_tp.gold.user_activity_report_days
REPLACE WHERE report_date = CAST(:run_date AS DATE)
-- The legacy reads these rows out of the serving Postgres that analytics_daily.py upserts
-- into. The target reads the Delta table that upsert is fed from (P3-D02), so the report
-- no longer depends on the serving leg having succeeded, and the dependency on
-- analytics_daily is a task edge rather than "it usually runs three hours earlier".
SELECT CAST(:run_date AS DATE) AS report_date,
       summary_date,
       active_users,
       active_documents,
       active_files,
       total_events,
       documents_created,
       documents_edited,
       comments_added,
       files_uploaded,
       files_shared,
       files_deleted,
       bytes_uploaded
FROM ow_tp.gold.analytics_daily_summary
WHERE summary_date BETWEEN date_sub(CAST(:run_date AS DATE), 30) AND CAST(:run_date AS DATE)
