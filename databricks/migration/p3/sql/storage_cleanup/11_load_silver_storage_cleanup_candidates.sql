-- Recompute the delete set for one batch from the landed inventory and metadata. REPLACE
-- WHERE swaps the batch in one commit, so a rerun on the same snapshot is a no-op rather
-- than a duplicate set.
--
-- The legacy's definition, clause by clause (Pipeline3_analytics_record_contract §4):
--
--   prefix      list_objects_v2 is called with Prefix='files/', so an object outside that
--               prefix is never a candidate however unreferenced it is. The thumbnails/
--               object in the snapshot is exactly that case and must stay out.
--   reference   the metadata scan projects s3_key and keeps the truthy ones, so a row with
--               a missing or empty s3_key references nothing. A reference pointing at an
--               object that is not in the listing (the snapshot carries five of those)
--               subtracts nothing and must not fail the job.
--   orphan      key in the listing, not in the reference set. No age test: the legacy has
--               none, and adding one would shrink the delete set.
--
-- NOT IN is avoided deliberately: a single NULL s3_key would make it return no rows at
-- all and the job would report an empty delete set as success. NOT EXISTS with an explicit
-- non-empty filter says what the legacy's `if key:` says.
INSERT INTO ow_tp.silver.storage_cleanup_candidates
REPLACE WHERE snapshot_batch = :batch
SELECT
  inv.snapshot_batch,
  CAST(:run_date AS DATE) AS run_date,
  inv.object_key,
  inv.size_bytes,
  concat('quarantined/', :run_date, '/', inv.object_key) AS quarantine_key,
  current_timestamp() AS computed_at
FROM ow_tp.bronze.p3_cleanup_inventory_raw AS inv
WHERE inv.snapshot_batch = :batch
  AND startswith(inv.object_key, 'files/')
  AND NOT EXISTS (
    SELECT 1
    FROM ow_tp.bronze.p3_cleanup_metadata_raw AS md
    WHERE md.snapshot_batch = inv.snapshot_batch
      AND md.s3_key IS NOT NULL
      AND md.s3_key <> ''
      AND md.s3_key = inv.object_key
  )
