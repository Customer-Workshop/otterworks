-- The delete set storage_cleanup_daily.py would act on, computed and kept instead of acted
-- on (P3-D03). Every row here is an object the legacy would have copied to quarantine and
-- then deleted from the file-storage bucket.
--
-- size_bytes is part of the identity of a candidate, not a detail of it. The legacy copies
-- before it deletes, so a copy that silently truncated would still leave the key present
-- in quarantine; comparing keys alone would call that a match. The recon compares
-- (object_key, size_bytes) as a set for the same reason.
--
-- quarantine_key records where the legacy would have put the object, so the delete set can
-- be reviewed as the actual pair of operations rather than as a list of keys. Nothing in
-- this unit performs either operation.
CREATE TABLE IF NOT EXISTS ow_tp.silver.storage_cleanup_candidates (
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot the candidate set was computed from',
  run_date DATE NOT NULL COMMENT 'explicit execution date (P3-D08); the legacy dated itself from datetime.now()',
  object_key STRING NOT NULL COMMENT 'key in the file-storage bucket, under the files/ prefix',
  size_bytes BIGINT NOT NULL COMMENT 'size as listed; part of the comparison key',
  quarantine_key STRING NOT NULL COMMENT 'quarantined/<run_date>/<object_key>, the destination the legacy copies to',
  computed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Orphaned-object delete set, computed and persisted. P3-D03: this unit never deletes and never copies; deletion is a separate human-enabled action gated on exact set equality with the legacy delete set.'
