-- The eleven counters the legacy wrote, recomputed as one query over silver.
--
-- Event types are matched as exact literals (F-0.9): analytics-service's dotted
-- `document.created` raises total_events and nothing else, exactly as the legacy's
-- `df["eventType"] == "document_created"` comparison does. Normalising the two
-- vocabularies would change the numbers.
--
-- active_documents and active_files are set unions across event types, and they drop
-- NULL ids the way `.dropna().unique()` does. bytes_uploaded sums sizeBytes over uploads
-- with absent values counted as zero (`fillna(0)`).
INSERT INTO ow_tp.gold.analytics_daily_summary
REPLACE WHERE summary_date = CAST(:run_date AS DATE)
SELECT
  summary_date,
  count(*) AS total_events,
  count(DISTINCT CASE WHEN resolved_user_id <> 'unknown' THEN resolved_user_id END) AS active_users,
  count_if(event_type = 'document_created') AS documents_created,
  count_if(event_type = 'document_edited') AS documents_edited,
  count_if(event_type = 'comment_added') AS comments_added,
  count_if(event_type = 'file_uploaded') AS files_uploaded,
  count_if(event_type = 'file_shared') AS files_shared,
  count_if(event_type = 'file_deleted') AS files_deleted,
  coalesce(sum(CASE WHEN event_type = 'file_uploaded' THEN coalesce(size_bytes, 0) END), 0)
    AS bytes_uploaded,
  count(DISTINCT CASE WHEN event_type IN ('document_created', 'document_edited')
                      THEN document_id END) AS active_documents,
  count(DISTINCT CASE WHEN event_type IN ('file_uploaded', 'file_shared', 'file_deleted')
                      THEN file_id END) AS active_files
FROM ow_tp.silver.analytics_events_daily
WHERE summary_date = CAST(:run_date AS DATE) AND snapshot_batch = :batch
GROUP BY summary_date
