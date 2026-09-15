-- Build the compliance report from what was actually archived, not from a counter kept
-- while archiving. The legacy reports len(events_to_archive) for both events_scanned and
-- events_archived, so the two agree there by construction; deriving them from the archive
-- table keeps that true here and makes the report a statement about committed rows rather
-- than about an in-memory list.
--
-- GROUP BY probe_shape is what drops the shape that archived nothing: no archived rows,
-- no group, no report row. That is the F-0.4 behaviour, reproduced by the shape of the
-- query instead of by a special case.
INSERT INTO ow_tp.silver.audit_archive_run
REPLACE WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE)
SELECT
  ar.snapshot_batch,
  ar.run_date,
  ar.probe_shape,
  90 AS retention_days,
  concat(CAST(date_sub(CAST(:run_date AS DATE), 90) AS STRING), 'T00:00:00Z') AS cutoff_date,
  count(*) AS events_scanned,
  count(*) AS events_archived,
  0 AS events_deleted_from_source,
  'ow_tp.silver.audit_archive' AS archive_location,
  current_timestamp() AS generated_at
FROM ow_tp.silver.audit_archive AS ar
WHERE ar.snapshot_batch = :batch
  AND ar.run_date = CAST(:run_date AS DATE)
GROUP BY ar.snapshot_batch, ar.run_date, ar.probe_shape
