-- The compliance report the legacy writes to S3 as JSON, as a row per run and shape.
--
-- events_deleted_from_source is a column rather than a constant in a template because it
-- is the number the report is read for. The legacy prints 0 there for a reason it does not
-- know about (every delete_item raises on the wrong key schema and the exception is
-- swallowed); the converted job prints 0 because P3-D04 says it must not delete. Same
-- number, different reason, and the STOP E packet says so.
--
-- The legacy report also carries four booleans (gdpr_compliant, soc2_compliant,
-- data_encrypted_at_rest, data_encrypted_in_transit) hard-coded to true. They are
-- assertions the script makes about itself, not measurements, and the converted job does
-- not restate them: a column that always reads true tells a compliance reader nothing and
-- would carry a legacy claim onto a new platform it was never made about. The omission is
-- declared in the recon report rather than passed off as a match.
--
-- A shape that archived nothing gets no row, which is how the legacy behaves: it exits
-- before the report when the scan matches nothing (F-0.4), so there is no compliance
-- report for the A-estate shape on either side.
CREATE TABLE IF NOT EXISTS ow_tp.silver.audit_archive_run (
  snapshot_batch STRING NOT NULL,
  run_date DATE NOT NULL COMMENT 'explicit execution date (P3-D08)',
  probe_shape STRING NOT NULL,
  retention_days INT NOT NULL COMMENT '90, as in the legacy',
  cutoff_date STRING NOT NULL COMMENT 'the cutoff string the selection compared against, kept verbatim for audit',
  events_scanned BIGINT NOT NULL COMMENT 'records the legacy scan would have matched; equal to events_archived, as in the legacy report',
  events_archived BIGINT NOT NULL,
  events_deleted_from_source BIGINT NOT NULL COMMENT 'always 0: the converted job never deletes (P3-D04)',
  archive_location STRING NOT NULL COMMENT 'the Delta table holding the bodies, where the legacy named an s3:// Glacier object',
  generated_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Audit-archive compliance report. One row per run per record shape; no row where nothing was archived.'
