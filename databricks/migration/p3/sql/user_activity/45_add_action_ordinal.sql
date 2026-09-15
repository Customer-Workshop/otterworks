-- The key order of `actions_by_type` in the legacy report, kept alongside the counts.
-- A workspace that already holds this table from before the export existed keeps its old
-- schema, because the create above is IF NOT EXISTS, so the column is added in place.
--
-- Databricks has no ADD COLUMN IF NOT EXISTS, and a bare ADD COLUMN fails the task on the
-- second run, so the add is guarded on the catalog rather than on an error.
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ow_tp.information_schema.columns
                 WHERE table_schema = 'gold'
                   AND table_name = 'user_activity_user_actions'
                   AND column_name = 'action_ordinal') THEN
    ALTER TABLE ow_tp.gold.user_activity_user_actions
    ADD COLUMN action_ordinal INT
    COMMENT 'position of this key inside the users actions_by_type object, 1-based';
  END IF;
END
