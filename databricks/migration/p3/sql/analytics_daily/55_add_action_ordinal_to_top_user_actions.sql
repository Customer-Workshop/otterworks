-- A workspace that already holds this table from before the key order was recorded keeps
-- its old schema, because the create above is IF NOT EXISTS. The column is added in place
-- rather than by recreating the table, so no other namespace loses its rows.
--
-- The order is not a number the report needs; it is the order the legacy's own
-- `top_users.jsonl.gz` record writes its `actions` keys in, and user_activity_daily.py
-- carries it forward into `actions_by_type`. Gold aggregates it away, so without this
-- column a day older than silver's retention has no recoverable key order.
--
-- Databricks has no ADD COLUMN IF NOT EXISTS, and a bare ADD COLUMN fails the task on the
-- second run, so the add is guarded on the catalog rather than on an error.
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ow_tp.information_schema.columns
                 WHERE table_schema = 'gold'
                   AND table_name = 'analytics_daily_top_user_actions'
                   AND column_name = 'action_ordinal') THEN
    ALTER TABLE ow_tp.gold.analytics_daily_top_user_actions
    ADD COLUMN action_ordinal INT
    COMMENT 'position of this key inside the records actions object, 1-based';
  END IF;
END
