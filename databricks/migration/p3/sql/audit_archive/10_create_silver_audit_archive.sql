-- The set of audit events audit_archive_weekly.py would have archived, kept as rows
-- instead of as a gzip object in Glacier.
--
-- The legacy writes one JSONL.gz per run with StorageClass=GLACIER, which cannot be read
-- back without a restore first (the wave-0 baseline capture had to issue one). The
-- converted unit keeps the same bodies in Delta: same rows, readable by the compliance
-- reader without a thaw. That is a deliberate difference in medium, not in content, and
-- it is what the recon compares.
--
-- payload_json is the whole archived record, canonicalised (sorted keys, compact
-- separators) so the two sides compare as strings. archived_timestamp is the lowercase
-- `timestamp` attribute the legacy filtered on, kept next to the body because it is the
-- reason the row is here at all.
--
-- P3-D04: nothing in this unit deletes from the source table. The legacy tries and fails
-- (it builds a key of event_id + timestamp against a table keyed otherwise, and the
-- exception is swallowed), so both sides archive and neither prunes.
CREATE TABLE IF NOT EXISTS ow_tp.silver.audit_archive (
  snapshot_batch STRING NOT NULL COMMENT 'immutable input snapshot the archive set was computed from',
  run_date DATE NOT NULL COMMENT 'explicit execution date (P3-D08); the legacy dated itself from datetime.now()',
  probe_shape STRING NOT NULL COMMENT 'A-estate | A-tsonly | A-full; part of the key because one logical event exists in several shapes',
  event_id STRING NOT NULL COMMENT 'event_id when the record carries one, else its id',
  archived_timestamp STRING COMMENT 'the lowercase timestamp attribute, exactly as the record carried it',
  payload_json STRING NOT NULL COMMENT 'the archived record body as canonical JSON',
  archived_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Archived audit events. Replaces the Glacier JSONL.gz object with governed Delta rows; no source deletion (P3-D04).'
