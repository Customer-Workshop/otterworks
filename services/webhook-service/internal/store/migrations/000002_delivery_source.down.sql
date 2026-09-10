DROP INDEX IF EXISTS webhook.deliveries_source_unique;
ALTER TABLE webhook.deliveries DROP COLUMN IF EXISTS source_message_id;
