-- Recompute the archive set for one batch from the landed scan. REPLACE WHERE swaps the
-- batch and date in one commit, so a rerun on the same snapshot is a no-op rather than a
-- second copy of the same events.
--
-- The legacy's selection, clause by clause (Pipeline3_analytics_record_contract §5):
--
--   attribute   the DynamoDB scan filters on `timestamp`, lowercase. A record that carries
--               `Timestamp` and no `timestamp` is not "timestamp is null" to DynamoDB, it
--               is "attribute does not exist", and the filter never matches it. That is
--               F-0.4: against the shape the audit-service really writes, the legacy
--               archives nothing at all. ts_attr IS NOT NULL says the same thing here, and
--               coalescing it with the other casing would archive records the legacy left
--               untouched.
--   cutoff      run_date minus 90 days, rendered as the legacy renders it
--               ('YYYY-MM-DDT00:00:00Z') and compared as a string, because DynamoDB
--               compares the stored strings. Parsing both sides into timestamps would be a
--               different function: it would match records whose timestamp is written in
--               another ISO form, which the legacy's string compare skips.
--   strictness  strictly less than the cutoff. A record exactly at the cutoff instant stays
--               in the source, and the snapshot carries that boundary pair on purpose.
INSERT INTO ow_tp.silver.audit_archive
REPLACE WHERE snapshot_batch = :batch AND run_date = CAST(:run_date AS DATE)
SELECT
  ev.snapshot_batch,
  CAST(:run_date AS DATE) AS run_date,
  ev.probe_shape,
  ev.event_id,
  ev.ts_attr AS archived_timestamp,
  ev.payload_json,
  current_timestamp() AS archived_at
FROM ow_tp.bronze.p3_audit_events_raw AS ev
WHERE ev.snapshot_batch = :batch
  AND ev.ts_attr IS NOT NULL
  AND ev.ts_attr < concat(CAST(date_sub(CAST(:run_date AS DATE), 90) AS STRING), 'T00:00:00Z')
